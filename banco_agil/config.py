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
    """Garante o dialeto assíncrono `psycopg_async` do psycopg3.

    O Team/AgentOS roda num event loop assíncrono (FastAPI); usar um
    PostgresDb síncrono dentro dele bloqueia o worker inteiro na primeira
    escrita real (trava o processo, inclusive o /health). O Agno recomenda
    `AsyncPostgresDb` com `postgresql+psycopg_async://` para esse caso
    (https://docs.agno.com/database/providers/async-postgres/overview).

    O plugin Postgres do Railway (e o `psql` em geral) injeta a URL no
    formato padrão `postgresql://` ou `postgresql+psycopg://` — normalizamos
    qualquer um desses para o dialeto assíncrono.
    """
    for prefixo in ("postgresql+psycopg://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg_async://" + url[len(prefixo):]
    return url


# Railway injeta a URL do plugin Postgres como DATABASE_URL; localmente
# usamos DB_URL (via .env / docker-compose).
DB_URL = _normalizar_db_url(
    os.getenv("DB_URL")
    or os.getenv("DATABASE_URL")
    or "postgresql+psycopg_async://banco:agil_dev_pw@localhost:5432/banco_agil"
)

# ── Modelos LLM (DeepInfra) ──────────────────────────────────────────────────
COORDINATOR_MODEL_ID = os.getenv(
    "COORDINATOR_MODEL_ID",
    "zai-org/GLM-5.2",
)
SPECIALIST_MODEL_ID = os.getenv(
    "SPECIALIST_MODEL_ID",
    "deepseek-ai/DeepSeek-V3-0324",
)


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
