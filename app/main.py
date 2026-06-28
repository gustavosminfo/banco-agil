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
    # auto_provision_dbs trava no lifespan de startup contra o Postgres do
    # Railway (mesmo com AsyncPostgresDb) — o AsyncPostgresDb do Team já
    # cria as tabelas sob demanda na primeira escrita real.
    auto_provision_dbs=False,
)

app = agent_os.get_app()
