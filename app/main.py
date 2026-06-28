"""
app/main.py
Entry point do AgentOS — registra o Team "Banco Ágil" e serve REST/SSE.

Execução local:
    uvicorn app.main:app --reload
"""

import logging
import os

from agno.os import AgentOS

from banco_agil.team import criar_equipe

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

team = criar_equipe()

agent_os = AgentOS(
    name="Banco Ágil",
    teams=[team],
    tracing=True,
    telemetry=os.getenv("AGNO_TELEMETRY", "true").lower() == "true",
    # O PostgresDb do Team já garante a criação das tabelas sob demanda;
    # o auto-provisionamento assíncrono do AgentOS no lifespan de startup
    # travava indefinidamente nesta combinação (Postgres do Railway).
    auto_provision_dbs=False,
)

app = agent_os.get_app()
