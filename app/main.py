"""
app/main.py
Entry point do AgentOS — registra o Team "Banco Ágil" e serve REST/SSE.

Execução local:
    uvicorn app.main:app --reload
"""

import logging
import os

from agno.db.postgres import PostgresDb
from agno.os import AgentOS
from agno.registry import Registry

from banco_agil.agents import cambio_agent, credito_agent, entrevista_agent, triagem_agent
from banco_agil.config import DB_URL
from banco_agil.team import criar_equipe

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

team = criar_equipe()

# Registra nossos agentes e o Team de produção como peças reutilizáveis no
# Studio (montar Teams/Workflows NOVOS no Studio, em modo de experimento) —
# deliberadamente NÃO usamos o Studio para editar/publicar a lógica de
# produção em si: ela continua 100% definida em código e versionada no Git,
# para manter trilha de auditoria revisável (PRs), essencial num contexto
# bancário. Ver docs/runbook.md.
registry = Registry(
    name="Banco Ágil",
    agents=[triagem_agent, credito_agent, entrevista_agent, cambio_agent],
    teams=[team],
)

agent_os = AgentOS(
    name="Banco Ágil",
    teams=[team],
    registry=registry,
    # Sem isso, Studio/Approvals/Scheduler/Metrics/Evals ficam indisponíveis
    # no painel do os.agno.com ("pass a db to AgentOS to enable this
    # feature"). PostgresDb síncrono — exigido pelo Studio (Components) e
    # recomendado pela documentação oficial do Agno como banco de produção.
    # Instância separada da do Team — mesma URL, pool próprio.
    db=PostgresDb(db_url=DB_URL),
    scheduler=True,
    tracing=True,
    telemetry=os.getenv("AGNO_TELEMETRY", "true").lower() == "true",
    # auto_provision_dbs travou o lifespan de startup em produção — não por
    # ser síncrono/assíncrono, mas por um volume do Postgres mal anexado na
    # Railway (já corrigido). Mantido desligado: o PostgresDb do Team já
    # cria as tabelas sob demanda na primeira escrita real.
    auto_provision_dbs=False,
)

app = agent_os.get_app()
