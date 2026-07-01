"""
banco_agil/media_processing.py
Pré-processamento de mídia do canal WhatsApp (áudio, imagem) em texto puro,
via modelos DeepInfra dedicados — ANTES de a mensagem chegar ao coordenador
(GLM-5.2, text-only). Isso mantém o Team e os agentes 100% inalterados: eles
nunca veem uma imagem ou um áudio, só o texto resultante.
"""

import base64
import logging
import os

import httpx

from banco_agil.config import STT_MODEL_ID, VISION_MODEL_ID

logger = logging.getLogger(__name__)

DEEPINFRA_API_KEY = os.getenv("DEEPINFRA_API_KEY", "")

_DEEPINFRA_STT_URL = "https://api.deepinfra.com/v1/inference/{model_id}"
_DEEPINFRA_CHAT_URL = "https://api.deepinfra.com/v1/openai/chat/completions"


def transcrever_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """
    Transcreve áudio para texto via DeepInfra (Whisper).

    Args:
        audio_bytes: Conteúdo bruto do arquivo de áudio.
        mime_type:   Content-type do arquivo (ex.: "audio/ogg" — formato
                     padrão de notas de voz do WhatsApp).

    Returns:
        Texto transcrito. String vazia em caso de falha (o chamador deve
        tratar como "não foi possível processar o áudio").
    """
    url = _DEEPINFRA_STT_URL.format(model_id=STT_MODEL_ID)
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"bearer {DEEPINFRA_API_KEY}"},
            files={"audio": ("audio", audio_bytes, mime_type)},
            timeout=60.0,
        )
        resp.raise_for_status()
        return str(resp.json().get("text", "")).strip()
    except Exception:
        logger.exception("Falha ao transcrever áudio via DeepInfra (%s)", STT_MODEL_ID)
        return ""


def descrever_imagem(image_bytes: bytes, mime_type: str = "image/jpeg", legenda: str | None = None) -> str:
    """
    Gera uma descrição textual de uma imagem via modelo de visão da DeepInfra
    (endpoint OpenAI-compatible, mesmo padrão usado por DeepInfra/OpenAILike
    em banco_agil/config.py).

    Args:
        image_bytes: Conteúdo bruto da imagem.
        mime_type:   Content-type da imagem (ex.: "image/jpeg", "image/webp"
                     para stickers).
        legenda:     Legenda opcional enviada junto com a imagem pelo cliente.

    Returns:
        Descrição textual da imagem, combinada com a legenda se houver.
        String vazia em caso de falha.
    """
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{image_b64}"

    prompt = (
        "Descreva esta imagem em português, de forma objetiva, indicando "
        "qualquer texto visível (ex.: documentos, comprovantes, capturas de "
        "tela). Se for uma figurinha/sticker, descreva a expressão ou "
        "mensagem que ela transmite."
    )

    try:
        resp = httpx.post(
            _DEEPINFRA_CHAT_URL,
            headers={
                "Authorization": f"Bearer {DEEPINFRA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": VISION_MODEL_ID,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
                "max_tokens": 500,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        descricao = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        logger.exception("Falha ao descrever imagem via DeepInfra (%s)", VISION_MODEL_ID)
        return ""

    if legenda:
        return f"[Imagem enviada pelo cliente: {descricao}]\nLegenda do cliente: {legenda}"
    return f"[Imagem enviada pelo cliente: {descricao}]"
