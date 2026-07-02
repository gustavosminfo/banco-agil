"""
banco_agil/config.py
Configurações centralizadas do Banco Ágil.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from agno.models.deepinfra import DeepInfra

load_dotenv()

# ── Caminhos ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

CLIENTES_CSV = DATA_DIR / "clientes.csv"
SCORE_LIMITE_CSV = DATA_DIR / "score_limite.csv"
SOLICITACOES_CSV = DATA_DIR / "solicitacoes_aumento_limite.csv"

# ── Banco de dados (sessão/tracing do AgentOS) ───────────────────────────────
def _normalizar_db_url(url: str) -> str:
    """Garante o dialeto síncrono `psycopg` (psycopg3) do PostgresDb.

    `PostgresDb` é "o banco de produção recomendado" pela documentação
    oficial do Agno (https://docs.agno.com/features/storage#pick-a-backend),
    usado diretamente nos próprios exemplos de AgentOS+FastAPI sem ressalvas.
    Um travamento real de startup que tivemos em produção foi diagnosticado
    (incorretamente, na época) como "PostgresDb síncrono bloqueia o event
    loop" — mas a troca para `AsyncPostgresDb` não resolveu o travamento
    (confirmado pela própria mensagem do commit que fez essa troca); a causa
    real era um volume do Postgres mal anexado na Railway + `auto_provision_dbs`
    do AgentOS, ambos corrigidos separadamente.

    O plugin Postgres do Railway (e o `psql` em geral) injeta a URL no
    formato padrão `postgresql://` — normalizamos para o dialeto síncrono
    explícito.
    """
    for prefixo in ("postgresql+psycopg_async://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo):]
    return url


# Railway injeta a URL do plugin Postgres como DATABASE_URL; localmente
# usamos DB_URL (via .env / docker-compose).
DB_URL = _normalizar_db_url(
    os.getenv("DB_URL")
    or os.getenv("DATABASE_URL")
    or "postgresql+psycopg://banco:agil_dev_pw@localhost:5432/banco_agil"
)

# URL pública do Postgres da Railway, usada apenas por `python -m evals
# --remote` para persistir os resultados no mesmo banco do AgentOS de
# produção (popula a aba Evaluation do os.agno.com). Opcional — sem ela,
# os evals continuam funcionando normalmente, só sem essa persistência.
_eval_db_url_raw = os.getenv("EVAL_DB_URL")
EVAL_DB_URL = _normalizar_db_url(_eval_db_url_raw) if _eval_db_url_raw else None

# ── Modelos LLM (DeepInfra) ──────────────────────────────────────────────────
COORDINATOR_MODEL_ID = os.getenv(
    "COORDINATOR_MODEL_ID",
    "zai-org/GLM-5.2",
)
SPECIALIST_MODEL_ID = os.getenv(
    "SPECIALIST_MODEL_ID",
    "deepseek-ai/DeepSeek-V3-0324",
)
# Usados só pelo canal WhatsApp (banco_agil/media_processing.py) para
# converter áudio/imagem em texto ANTES de chegar ao coordenador — que
# permanece text-only (GLM-5.2 não suporta multimodal).
STT_MODEL_ID = os.getenv("STT_MODEL_ID", "openai/whisper-large-v3-turbo")
VISION_MODEL_ID = os.getenv("VISION_MODEL_ID", "google/gemma-4-31B-it")


def get_coordinator_model() -> DeepInfra:
    """Modelo usado por todos os agentes e pelo Team coordinator.

    GLM-5.2 (não "Thinking") substituiu o Qwen3-235B-A22B-Thinking-2507 em
    produção: o modelo de raciocínio visível ocasionalmente entrava num loop
    de raciocínio interno repetitivo ("wait, no... wait, but...") até esgotar
    o orçamento de tokens, retornando uma resposta final vazia ou excedendo
    o timeout de gateway da Railway (300s) — observado repetidas vezes em
    produção mesmo após mitigações (max_iterations, max_tokens maior).
    GLM-5.2 não exibiu esse comportamento nos mesmos cenários de teste."""
    return DeepInfra(
        id=COORDINATOR_MODEL_ID,
        temperature=0.3,
        max_tokens=6000,
    )


def get_specialist_model() -> DeepInfra:
    """Modelo mais barato (tool calling simples). Atualmente nenhum agente o usa —
    todos foram promovidos para get_coordinator_model() após falhas reais de
    tool-calling em produção (ver AGENTS.md). Mantido para uso futuro."""
    return DeepInfra(
        id=SPECIALIST_MODEL_ID,
        temperature=0.5,
        max_tokens=1500,
    )


# ── Regras de negócio ────────────────────────────────────────────────────────
MAX_AUTH_ATTEMPTS = 3  # Tentativas de autenticação antes do bloqueio

# ── API de Câmbio (AwesomeAPI) ───────────────────────────────────────────────
# Funciona sem chave (cache de 1min, rate limit baixo) ou com AWESOMEAPI_TOKEN
# (100k requisições/mês grátis — https://docs.awesomeapi.com.br/instrucoes-api-key).
CAMBIO_API_URL = "https://economia.awesomeapi.com.br/json/last/{pair}"
# Exemplos de par: USD-BRL, EUR-BRL, GBP-BRL, BTC-BRL
AWESOMEAPI_TOKEN = os.getenv("AWESOMEAPI_TOKEN", "")

# ── Mapeamento de nomes de moeda para par AwesomeAPI ─────────────────────────
MOEDA_PARA_PAR: dict[str, str] = {
    "dolar": "USD-BRL",
    "dólar": "USD-BRL",
    "usd": "USD-BRL",
    "euro": "EUR-BRL",
    "eur": "EUR-BRL",
    "libra": "GBP-BRL",
    "gbp": "GBP-BRL",
    "bitcoin": "BTC-BRL",
    "btc": "BTC-BRL",
    "iene": "JPY-BRL",
    "jpy": "JPY-BRL",
}

# ── Canal WhatsApp (Kapso) ────────────────────────────────────────────────────
# API REST + webhooks pura da Kapso (sem SDK — Chat SDK é TypeScript-only).
KAPSO_API_KEY = os.getenv("KAPSO_API_KEY", "")
KAPSO_WEBHOOK_SECRET = os.getenv("KAPSO_WEBHOOK_SECRET", "")
KAPSO_PHONE_NUMBER_ID = os.getenv("KAPSO_PHONE_NUMBER_ID", "")
KAPSO_API_BASE = "https://api.kapso.ai/meta/whatsapp/v24.0"
# API de plataforma da Kapso (distinta da API Meta/WhatsApp acima) — usada
# para gerenciar o estado da conversa em si (ex.: encerrar), não mensagens.
KAPSO_PLATFORM_API_BASE = "https://api.kapso.ai/platform/v1"
