"""
app/routers/kapso_webhook.py
Recebe webhooks da Kapso (WhatsApp Business API) — verifica assinatura,
faz ack imediato e delega o processamento pesado (que pode levar minutos,
ver ui/api_client.py) para uma BackgroundTask, evitando retry agressivo do
lado da Kapso por timeout.
"""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from banco_agil.channels import kapso_processing
from banco_agil.config import KAPSO_WEBHOOK_SECRET

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["kapso"])


def _verificar_assinatura(raw_body: bytes, assinatura_recebida: str) -> bool:
    if not KAPSO_WEBHOOK_SECRET or not assinatura_recebida:
        return False
    esperado = hmac.new(
        KAPSO_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(esperado, assinatura_recebida)


@router.post("/kapso")
async def receber_webhook_kapso(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()  # bytes crus — obrigatório para o HMAC, antes de qualquer parse
    assinatura = request.headers.get("X-Webhook-Signature", "")

    if not _verificar_assinatura(raw_body, assinatura):
        logger.warning("Webhook Kapso: assinatura inválida ou ausente, requisição rejeitada.")
        raise HTTPException(status_code=401, detail="assinatura inválida")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="payload inválido")

    if payload.get("event") != "whatsapp.message.received":
        # Diagnóstico temporário: o formato exato do payload da Kapso ainda
        # está sendo validado (item de spike do plano) — logar só a
        # ESTRUTURA (chaves/tipos, nunca valores como texto de mensagem ou
        # telefone) ajuda a confirmar o formato real sem expor PII.
        def _estrutura(v, profundidade=5):
            if profundidade <= 0:
                return type(v).__name__
            if isinstance(v, dict):
                return {k: _estrutura(v[k], profundidade - 1) for k in v}
            if isinstance(v, list):
                return [f"list[{len(v)}]"] + ([_estrutura(v[0], profundidade - 1)] if v else [])
            return type(v).__name__

        logger.warning(
            "Webhook Kapso ignorado — payload.get('type')=%r, estrutura=%s",
            payload.get("type"),
            _estrutura(payload),
        )
        return {"status": "ignorado"}

    logger.info(
        "Webhook Kapso aceito — message.type=%r, chaves de message=%s",
        (payload.get("message") or {}).get("type"),
        list((payload.get("message") or {}).keys()),
    )

    # Ack imediato — processamento real roda em background (evita timeout
    # de webhook e retry agressivo do lado da Kapso).
    background_tasks.add_task(kapso_processing.processar_mensagem, payload)
    return {"status": "recebido"}
