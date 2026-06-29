"""
app/main.py
Entry point do AgentOS — registra o Team "Banco Ágil" e serve REST/SSE.

Execução local:
    uvicorn app.main:app --reload
"""

import logging
import os

from agno.db.postgres import AsyncPostgresDb
from agno.os import AgentOS

from banco_agil.config import DB_URL
from banco_agil.team import criar_equipe

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

team = criar_equipe()

agent_os = AgentOS(
    name="Banco Ágil",
    teams=[team],
    # Sem isso, Studio/Approvals/Scheduler/Metrics/Evals ficam indisponíveis
    # no painel do os.agno.com ("pass a db to AgentOS to enable this
    # feature"). Instância separada da do Team — mesma URL, pool próprio.
    db=AsyncPostgresDb(db_url=DB_URL),
    scheduler=True,
    tracing=True,
    telemetry=os.getenv("AGNO_TELEMETRY", "true").lower() == "true",
    # auto_provision_dbs trava no lifespan de startup contra o Postgres do
    # Railway (mesmo com AsyncPostgresDb) — o AsyncPostgresDb do Team já
    # cria as tabelas sob demanda na primeira escrita real.
    auto_provision_dbs=False,
)

app = agent_os.get_app()
