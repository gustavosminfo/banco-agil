# ============================================================
# Banco Ágil — AgentOS Container
# Runtime: Agno AgentOS (FastAPI + uvicorn)
# Provider: DeepInfra (nenhuma dep Anthropic/OpenAI direta)
# ============================================================

# ── Stage 1: builder ─────────────────────────────────────────
FROM python:3.11-slim AS builder

# Metadados
LABEL maintainer="CoE IA Cogna <coe-ia@cogna.com.br>"
LABEL description="Banco Ágil — AgentOS Runtime"
LABEL version="1.0.0"

# Não interativo, locale br
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=C.UTF-8

WORKDIR /build

# Instalar deps de sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar manifesto de dependências primeiro (cache de layers)
COPY pyproject.toml ./
# Fallback: se pyproject.toml não existir ainda, usar requirements
COPY requirements.txt* ./

# Instalar dependências Python
RUN pip install --upgrade pip setuptools wheel && \
    if [ -f pyproject.toml ]; then \
        pip install -e ".[prod]"; \
    else \
        pip install -r requirements.txt; \
    fi


# ── Stage 2: runtime ─────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    # Desabilitar telemetria do Agno (dados ficam no nosso infra)
    AGNO_TELEMETRY=false \
    # Porta padrão (Railway sobrescreve com $PORT)
    PORT=8000

WORKDIR /app

# Deps de sistema para runtime (apenas runtime, sem build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar pacotes Python instalados do builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin

# Criar usuário não-root (segurança)
RUN groupadd -r agno && useradd -r -g agno -d /app -s /sbin/nologin agno

# Copiar código da aplicação
COPY --chown=agno:agno banco_agil/   ./banco_agil/
COPY --chown=agno:agno app/          ./app/
COPY --chown=agno:agno scripts/      ./scripts/

# Copiar dados CSV (base de clientes e score)
# Em produção com Postgres (Fase 2), este COPY pode ser removido
COPY --chown=agno:agno data/         ./data/

# Criar diretório tmp para SQLite local (dev/fallback)
RUN mkdir -p /app/tmp && chown agno:agno /app/tmp

# Mudar para usuário não-root
USER agno

# Health check — endpoint nativo do AgentOS
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expor porta (Railway usa $PORT dinamicamente)
EXPOSE ${PORT}

# Entrypoint — Railway sobrescreve PORT automaticamente
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --log-level info"]
