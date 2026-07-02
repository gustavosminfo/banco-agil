"""
banco_agil/channels/kapso_client.py
Cliente REST puro para a Kapso (WhatsApp Business API) — sem SDK, sem Node.js.
Mesmo padrão httpx curto/síncrono usado em banco_agil/tools/exchange_tools.py.
"""

import logging
import re

import httpx

from banco_agil.config import KAPSO_API_BASE, KAPSO_API_KEY

logger = logging.getLogger(__name__)

# O coordenador (markdown=True) responde em Markdown padrão (**negrito**),
# mas o WhatsApp usa um asterisco só (*negrito*) — **texto** chega ao
# cliente com os asteriscos duplicados literais em vez de negrito.
_MARKDOWN_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _markdown_para_whatsapp(texto: str) -> str:
    """Converte formatação Markdown para a sintaxe de formatação do WhatsApp."""
    return _MARKDOWN_BOLD.sub(r"*\1*", texto)


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
