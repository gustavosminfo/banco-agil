"""
banco_agil/channels/kapso_processing.py
Orquestração do canal WhatsApp: dispatch por tipo de mensagem, idempotência,
pré-processamento de mídia (STT/visão) e chamada ao Team — tudo em processo,
sem passar pelo endpoint HTTP /teams/{id}/runs (necessário para poder setar
`metadata=` no Team.arun(), não exposto por aquele endpoint).
"""

import logging
import re

import psycopg

from banco_agil import media_processing
from banco_agil.channels import kapso_client
from banco_agil.config import DB_URL, KAPSO_PHONE_NUMBER_ID
from banco_agil.team import (
    criar_equipe,
    detectar_encerramento,
    extrair_info_auth,
    limpar_tags_da_resposta,
)

logger = logging.getLogger(__name__)

_RESPOSTA_NAO_SUPORTADO = (
    "No momento ainda não conseguimos processar esse tipo de conteúdo por "
    "aqui. Pode me contar em texto ou áudio o que você precisa? 😊"
)

_TIPOS_IMAGEM = {"image", "sticker"}


def _dsn_psycopg(db_url: str) -> str:
    """Converte a URL no dialeto SQLAlchemy (postgresql+psycopg://) para o
    DSN puro que psycopg.connect() espera (postgresql://)."""
    return db_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _mascarar_cpf(cpf: str) -> str:
    """Mascara CPF para logging seguro — mesmo princípio da correção de PII
    na sidebar do Streamlit (nunca logar CPF em texto puro)."""
    digitos = re.sub(r"\D", "", cpf or "")
    if len(digitos) != 11:
        return "***"
    return f"***.***.**{digitos[-3:-2]}-{digitos[-2:]}"


def _garantir_tabela_idempotencia(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kapso_webhook_events (
            message_id  TEXT PRIMARY KEY,
            received_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.commit()


def _ja_processada(conn: psycopg.Connection, message_id: str) -> bool:
    """Registra o message_id como processado; retorna True se JÁ existia
    (webhook redelivery), False se é a primeira vez (segue o processamento)."""
    cur = conn.execute(
        "INSERT INTO kapso_webhook_events (message_id) VALUES (%s) "
        "ON CONFLICT DO NOTHING",
        (message_id,),
    )
    conn.commit()
    return cur.rowcount == 0


async def processar_mensagem(payload: dict) -> None:
    """Ponto de entrada chamado via BackgroundTasks pelo router do webhook.
    Nunca deixa exceção propagar (já estamos fora do ciclo request/response
    do FastAPI) — qualquer falha é logada e a função retorna silenciosamente.
    """
    try:
        await _processar_mensagem_interno(payload)
    except Exception:
        logger.exception("Falha não tratada ao processar mensagem do WhatsApp.")


async def _processar_mensagem_interno(payload: dict) -> None:
    message = payload.get("message") or {}
    conversation = payload.get("conversation") or {}

    message_id = message.get("id")
    message_type = message.get("type")
    telefone_cliente = message.get("from")
    conversation_id = conversation.get("id")
    phone_number_id = payload.get("phone_number_id") or KAPSO_PHONE_NUMBER_ID

    if not (message_id and message_type and telefone_cliente and conversation_id):
        logger.warning("Payload do webhook Kapso incompleto, ignorando: %s", list(payload.keys()))
        return

    # Idempotência: webhooks podem ser reentregues pela Kapso em caso de
    # timeout/retry — nunca processar (nem responder) a mesma mensagem 2x.
    dsn = _dsn_psycopg(DB_URL)
    with psycopg.connect(dsn) as conn:
        _garantir_tabela_idempotencia(conn)
        if _ja_processada(conn, message_id):
            logger.info("Mensagem %s já processada anteriormente, ignorando redelivery.", message_id)
            return

    mensagem_final = await _extrair_texto_da_mensagem(message, message_type, phone_number_id)
    if mensagem_final is None:
        # Tipo não suportado (vídeo/documento/desconhecido) — resposta fixa,
        # sem acionar o Team.
        kapso_client.enviar_mensagem(
            phone_number_id=phone_number_id,
            para=telefone_cliente,
            texto=_RESPOSTA_NAO_SUPORTADO,
            reply_to_wamid=message_id,
        )
        return

    if not mensagem_final.strip():
        logger.warning("Pré-processamento de mídia não retornou texto para message_id=%s.", message_id)
        kapso_client.enviar_mensagem(
            phone_number_id=phone_number_id,
            para=telefone_cliente,
            texto="Desculpe, não consegui processar esse conteúdo. Pode tentar novamente ou enviar em texto?",
            reply_to_wamid=message_id,
        )
        return

    session_id = f"wa-{conversation_id}"

    # Instância fresca do Team por request — mesmo padrão anti-contaminação
    # de session_state já usado pelo TeamFactory do AgentOS e por evals/__main__.py.
    #
    # `user_id` não é setado aqui: no Streamlit ele é derivado do CPF só
    # após a autenticação (nunca client-controlled), mas o Team só carrega o
    # session_state persistido (que já contém `cpf`, usado pelas tools via
    # `team=None`/`_verificar_autorizacao`) internamente durante o próprio
    # `arun()` — não há como lê-lo com segurança antes desta chamada sem
    # duplicar a lógica de carregamento de sessão do Agno. Como o
    # `session_id` já é estável por conversa do WhatsApp
    # (`f"wa-{conversation_id}"`), a continuidade de autenticação funciona
    # via session_state normalmente; a única perda é a memória de longo
    # prazo entre sessões diferentes do mesmo cliente (feature do Streamlit
    # não replicada aqui no MVP).
    team = criar_equipe()
    run = await team.arun(
        mensagem_final,
        session_id=session_id,
        metadata={
            "source": "whatsapp",
            "canal": "whatsapp",
            "telefone_e164": telefone_cliente,
        },
    )
    texto_bruto = str(run.content) if run.content else ""

    # Mesmo parsing de tags já usado por ui/streamlit_app.py e evals/__main__.py
    # — nenhuma lógica de coordenação é duplicada.
    dados_auth = extrair_info_auth(texto_bruto)
    if dados_auth:
        logger.info(
            "Cliente autenticado via WhatsApp (session=%s, cpf=%s).",
            session_id,
            _mascarar_cpf(dados_auth["cpf"]),
        )

    resposta_limpa = limpar_tags_da_resposta(texto_bruto)
    if not resposta_limpa.strip():
        resposta_limpa = "Desculpe, tivemos uma instabilidade temporária. Tente novamente em instantes."

    kapso_client.enviar_mensagem(
        phone_number_id=phone_number_id,
        para=telefone_cliente,
        texto=resposta_limpa,
        reply_to_wamid=message_id,
    )

    if detectar_encerramento(texto_bruto):
        logger.info("Sessão WhatsApp %s encerrada.", session_id)


async def _extrair_texto_da_mensagem(message: dict, message_type: str, phone_number_id: str) -> str | None:
    """Converte a mensagem recebida em texto puro para enviar ao Team.
    Retorna None para tipos não suportados no MVP (vídeo, documento, etc.)."""

    if message_type == "text":
        return str((message.get("text") or {}).get("body", ""))

    if message_type == "audio":
        return _processar_audio(message, phone_number_id)

    if message_type in _TIPOS_IMAGEM:
        return _processar_imagem(message, message_type, phone_number_id)

    # vídeo, documento, tipo desconhecido — fora do escopo do MVP
    return None


def _processar_audio(message: dict, phone_number_id: str) -> str:
    kapso_meta = message.get("kapso") or {}

    # Transcrição própria via DeepInfra tem prioridade (controle de
    # qualidade/modelo, conforme requisito do projeto); cai para o
    # transcript nativo da Kapso se o download ou a transcrição falharem.
    audio_info = message.get("audio") or {}
    baixado = kapso_client.baixar_midia(
        media_url_do_webhook=kapso_meta.get("media_url"),
        media_id=audio_info.get("id") or kapso_meta.get("media_id"),
        phone_number_id=phone_number_id,
    )
    if baixado:
        audio_bytes, mime_type = baixado
        texto = media_processing.transcrever_audio(audio_bytes, mime_type)
        if texto:
            return texto

    transcript_nativo = (kapso_meta.get("transcript") or {}).get("text")
    if transcript_nativo:
        logger.info("Usando transcript nativo da Kapso como fallback (DeepInfra falhou ou indisponível).")
        return str(transcript_nativo)

    return ""


def _processar_imagem(message: dict, message_type: str, phone_number_id: str) -> str:
    kapso_meta = message.get("kapso") or {}
    imagem_info = message.get(message_type) or {}
    legenda = imagem_info.get("caption")

    baixado = kapso_client.baixar_midia(
        media_url_do_webhook=kapso_meta.get("media_url"),
        media_id=imagem_info.get("id") or kapso_meta.get("media_id"),
        phone_number_id=phone_number_id,
    )
    if not baixado:
        return ""

    image_bytes, mime_type = baixado
    return media_processing.descrever_imagem(image_bytes, mime_type, legenda=legenda)
