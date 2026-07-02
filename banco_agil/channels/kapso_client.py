"""
banco_agil/channels/kapso_client.py
Cliente REST puro para a Kapso (WhatsApp Business API) — sem SDK, sem Node.js.
Mesmo padrão httpx curto/síncrono usado em banco_agil/tools/exchange_tools.py.
"""

import asyncio
import logging
import random
import re

import httpx

from banco_agil.config import KAPSO_API_BASE, KAPSO_API_KEY, KAPSO_PLATFORM_API_BASE

logger = logging.getLogger(__name__)

# O coordenador (markdown=True) responde em Markdown padrão (**negrito**),
# mas o WhatsApp usa um asterisco só (*negrito*) — **texto** chega ao
# cliente com os asteriscos duplicados literais em vez de negrito.
_MARKDOWN_BOLD = re.compile(r"\*\*(.+?)\*\*")

# Respostas longas ficam parcialmente ocultas no WhatsApp atrás de um botão
# "Ler mais" — dividimos em partes menores, respeitando parágrafos, para
# melhorar a legibilidade. Tamanho aproximado por parte (não é um limite
# rígido: um parágrafo isolado maior que isso nunca é cortado no meio).
_TAMANHO_ALVO_PARTE = 450
_DELAY_MIN_ENTRE_PARTES = 3.0
_DELAY_MAX_ENTRE_PARTES = 5.0


def _markdown_para_whatsapp(texto: str) -> str:
    """Converte formatação Markdown para a sintaxe de formatação do WhatsApp."""
    return _MARKDOWN_BOLD.sub(r"*\1*", texto)


def dividir_em_partes(texto: str, tamanho_alvo: int = _TAMANHO_ALVO_PARTE) -> list[str]:
    """
    Divide um texto longo em partes menores para envio como mensagens
    separadas no WhatsApp.

    Nunca corta no meio de um parágrafo (frase ou lista) — agrupa
    parágrafos consecutivos (separados por linha em branco) até que
    juntá-los ultrapasse `tamanho_alvo` caracteres, então inicia uma nova
    parte. Um parágrafo isolado maior que `tamanho_alvo` é mantido inteiro
    (nunca dividido no meio).
    """
    paragrafos = [p for p in texto.split("\n\n") if p.strip()]
    if not paragrafos:
        return [texto] if texto.strip() else []

    partes: list[str] = []
    atual: list[str] = []

    for paragrafo in paragrafos:
        candidato = "\n\n".join(atual + [paragrafo])
        if atual and len(candidato) > tamanho_alvo:
            partes.append("\n\n".join(atual))
            atual = [paragrafo]
        else:
            atual.append(paragrafo)

    if atual:
        partes.append("\n\n".join(atual))

    return partes


def enviar_mensagem(
    phone_number_id: str,
    para: str,
    texto: str,
    reply_to_wamid: str | None = None,
) -> dict:
    """
    Envia uma mensagem de texto via WhatsApp, usando a API REST da Kapso.

    Args:
        phone_number_id: ID do número WhatsApp Business que está respondendo.
        para:            Telefone do destinatário (E.164, sem "+", ex.: "5511999999999").
        texto:           Corpo da mensagem (já sem tags internas).
        reply_to_wamid:  ID (wamid) da mensagem original, para threading da resposta.

    Returns:
        dict com a resposta JSON da Kapso.
    """
    body: dict = {
        "messaging_product": "whatsapp",
        "to": para,
        "type": "text",
        "text": {"body": _markdown_para_whatsapp(texto)},
    }
    if reply_to_wamid:
        body["context"] = {"message_id": reply_to_wamid}

    resp = httpx.post(
        f"{KAPSO_API_BASE}/{phone_number_id}/messages",
        headers={"X-API-Key": KAPSO_API_KEY, "Content-Type": "application/json"},
        json=body,
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


async def enviar_mensagem_dividida(
    phone_number_id: str,
    para: str,
    texto: str,
    reply_to_wamid: str | None = None,
) -> None:
    """
    Envia uma resposta longa dividida em partes menores (ver dividir_em_partes),
    com um intervalo de alguns segundos entre cada parte — evita o botão
    "Ler mais" do WhatsApp e melhora a legibilidade. Para textos curtos
    (que já cabem em uma única parte), envia normalmente sem atraso extra.

    Só a primeira parte referencia `reply_to_wamid` (threading da resposta
    original); as partes seguintes são apenas continuação.
    """
    partes = dividir_em_partes(texto)
    if not partes:
        return

    for i, parte in enumerate(partes):
        enviar_mensagem(
            phone_number_id=phone_number_id,
            para=para,
            texto=parte,
            reply_to_wamid=reply_to_wamid if i == 0 else None,
        )
        if i < len(partes) - 1:
            await asyncio.sleep(random.uniform(_DELAY_MIN_ENTRE_PARTES, _DELAY_MAX_ENTRE_PARTES))


def marcar_como_lida_com_digitando(phone_number_id: str, message_id: str) -> None:
    """
    Marca a mensagem original como lida e exibe o indicador "digitando..."
    no WhatsApp do cliente enquanto o processamento (que pode levar minutos)
    está em andamento.

    O indicador some automaticamente ao enviarmos a resposta (enviar_mensagem)
    ou após ~25s, o que ocorrer primeiro — comportamento nativo da Kapso/Meta,
    não há como estendê-lo além disso.

    Falha aqui é apenas cosmética (o cliente não vê o indicador, mas o
    atendimento segue normalmente) — nunca deve interromper o processamento.
    """
    body = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"},
    }
    try:
        resp = httpx.post(
            f"{KAPSO_API_BASE}/{phone_number_id}/messages",
            headers={"X-API-Key": KAPSO_API_KEY, "Content-Type": "application/json"},
            json=body,
            timeout=10.0,
        )
        resp.raise_for_status()
    except Exception:
        logger.warning("Falha ao marcar mensagem como lida / exibir indicador de digitação.")


def encerrar_conversa(conversation_id: str) -> None:
    """
    Marca a conversa como encerrada ("ended") na Kapso — usado quando o
    Team chama a ferramenta encerrar_atendimento (tag [ENCERRADO] na
    resposta), para manter o estado da conversa sincronizado entre o
    Banco Ágil e o painel da Kapso.

    Falha aqui é apenas cosmética (não afeta o atendimento ao cliente, que
    já recebeu a mensagem de despedida) — nunca deve interromper o fluxo.
    """
    try:
        resp = httpx.patch(
            f"{KAPSO_PLATFORM_API_BASE}/whatsapp/conversations/{conversation_id}",
            headers={"X-API-Key": KAPSO_API_KEY, "Content-Type": "application/json"},
            json={"whatsapp_conversation": {"status": "ended"}},
            timeout=10.0,
        )
        resp.raise_for_status()
    except Exception:
        logger.warning("Falha ao encerrar conversa na Kapso (conversation_id=%s).", conversation_id)


def baixar_midia(
    media_url_do_webhook: str | None,
    media_id: str | None,
    phone_number_id: str,
) -> tuple[bytes, str] | None:
    """
    Baixa os bytes de uma mídia recebida via WhatsApp.

    Tenta primeiro `message.kapso.media_url` (já mirrorado pela Kapso no
    próprio payload do webhook — mais rápido, sem round-trip extra). Se
    ausente ou falhar, cai para o fluxo em duas etapas: obter a `download_url`
    (validade curta) via GET no endpoint de mídia, depois baixar os bytes.

    Returns:
        Tupla (bytes, mime_type) ou None em caso de falha.
    """
    if media_url_do_webhook:
        try:
            resp = httpx.get(media_url_do_webhook, timeout=30.0)
            resp.raise_for_status()
            mime_type = resp.headers.get("content-type", "application/octet-stream")
            return resp.content, mime_type
        except Exception:
            logger.warning("Falha ao baixar mídia via media_url do webhook, tentando fallback.")

    if not media_id:
        logger.error("Não foi possível baixar mídia: nem media_url nem media_id disponíveis.")
        return None

    try:
        meta_resp = httpx.get(
            f"{KAPSO_API_BASE}/{media_id}",
            headers={"X-API-Key": KAPSO_API_KEY},
            params={"phone_number_id": phone_number_id},
            timeout=15.0,
        )
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        download_url = meta.get("download_url")
        mime_type = meta.get("mime_type", "application/octet-stream")
        if not download_url:
            logger.error("Resposta de metadados de mídia sem download_url.")
            return None

        content_resp = httpx.get(download_url, timeout=30.0)
        content_resp.raise_for_status()
        return content_resp.content, mime_type
    except Exception:
        logger.exception("Falha ao baixar mídia via fallback (media_id=%s).", media_id)
        return None
