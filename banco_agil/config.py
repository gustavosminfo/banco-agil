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
    """Garante o dialeto psycopg3 (`postgresql+psycopg://`).

    O plugin Postgres do Railway (e o `psql` em geral) injeta a URL no
    formato padrão `postgresql://`, que o SQLAlchemy resolve para o driver
    `psycopg2` — não instalado neste projeto (usamos `psycopg` v3). Sem essa
    normalização, a conexão falha com `ModuleNotFoundError: psycopg2`.
    """
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


# Railway injeta a URL do plugin Postgres como DATABASE_URL; localmente
# usamos DB_URL (via .env / docker-compose).
DB_URL = _normalizar_db_url(
    os.getenv("DB_URL")
    or os.getenv("DATABASE_URL")
    or "postgresql+psycopg://banco:agil_dev_pw@localhost:5432/banco_agil"
)

# ── Modelos LLM (DeepInfra) ──────────────────────────────────────────────────
COORDINATOR_MODEL_ID = os.getenv(
    "COORDINATOR_MODEL_ID",
    "Qwen/Qwen3-235B-A22B-Thinking-2507",
)
SPECIALIST_MODEL_ID = os.getenv(
    "SPECIALIST_MODEL_ID",
    "deepseek-ai/DeepSeek-V3-0324",
)


def get_coordinator_model() -> DeepInfra:
    """Modelo usado pelo Team coordinator e pelo Agente de Entrevista (raciocínio)."""
    return DeepInfra(
        id=COORDINATOR_MODEL_ID,
        temperature=0.3,
        max_tokens=2000,
    )


def get_specialist_model() -> DeepInfra:
    """Modelo usado por Triagem, Crédito e Câmbio (tool calling simples, barato)."""
    return DeepInfra(
        id=SPECIALIST_MODEL_ID,
        temperature=0.5,
        max_tokens=1500,
    )


# ── Regras de negócio ────────────────────────────────────────────────────────
MAX_AUTH_ATTEMPTS = 3  # Tentativas de autenticação antes do bloqueio

# ── API de Câmbio (AwesomeAPI — gratuita, sem chave) ────────────────────────
CAMBIO_API_URL = "https://economia.awesomeapi.com.br/json/last/{pair}"
# Exemplos de par: USD-BRL, EUR-BRL, GBP-BRL, BTC-BRL

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
