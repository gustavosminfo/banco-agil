"""
app/routers/vapi_webhook.py
Recebe webhooks da VAPI.AI (canal de Ligação) — verifica o segredo do
servidor, despacha `tool-calls` para banco_agil/channels/vapi_processing.py e
responde SINCRONAMENTE (a VAPI está no meio de uma ligação de voz esperando
o resultado da tool para continuar a conversa — diferente do webhook da
Kapso, que faz ack imediato + BackgroundTask).
"""

import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from banco_agil.channels import vapi_processing
from banco_agil.config import VAPI_SERVER_SECRET

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["vapi"])

_EVENTOS_FIM_DE_CHAMADA = {"status-update", "end-of-call-report"}


def _verificar_segredo(segredo_recebido: str) -> bool:
    if not VAPI_SERVER_SECRET or not segredo_recebido:
        return False
    return hmac.compare_digest(segredo_recebido, VAPI_SERVER_SECRET)


@router.post("/vapi/tools")
async def receber_webhook_vapi(request: Request):
    segredo = request.headers.get("X-Vapi-Secret", "")
    if not _verificar_segredo(segredo):
        logger.warning("Webhook VAPI: segredo inválido ou ausente, requisição rejeitada.")
        raise HTTPException(status_code=401, detail="não autorizado")

    try:
        payload = json.loads(await request.body())
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="payload inválido")

    message = payload.get("message") or {}
    tipo = message.get("type")

    if tipo == "tool-calls":
        resultados = await vapi_processing.processar_tool_calls(message)
        return {"results": resultados}

    if tipo in _EVENTOS_FIM_DE_CHAMADA:
        await vapi_processing.processar_fim_de_chamada(message)
        return {}

    # Demais eventos de servidor (transcript, speech-update, conversation-update
    # etc.) não exigem resposta nem processamento neste MVP.
    logger.debug("Webhook VAPI ignorado — message.type=%r (evento não tratado).", tipo)
    return {}
