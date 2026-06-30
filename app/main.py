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
from banco_agil.config import DB_URL, get_coordinator_model
from banco_agil.team import criar_equipe
from banco_agil.tools.auth_tools import autenticar_cliente, buscar_dados_cliente
from banco_agil.tools.credit_tools import (
    consultar_limite_credito,
    solicitar_aumento_limite,
    verificar_limite_pelo_score,
)
from banco_agil.tools.exchange_tools import consultar_cotacao, listar_moedas_suportadas
from banco_agil.tools.interview_tools import atualizar_score_cliente, calcular_score_credito
from banco_agil.tools.session_tools import encerrar_atendimento

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

team = criar_equipe()

# Registry expõe tools, model, agentes e Team como building blocks no Studio:
# - tools e models → dropdowns ao criar/editar agentes no Studio
# - agents e teams → membros disponíveis ao montar novos Teams/Workflows
# Para publicar os agentes atuais como itens editáveis no Studio, execute:
#   python scripts/sync_to_studio.py
registry = Registry(
    name="Banco Ágil",
    tools=[
        # Autenticação
        autenticar_cliente,
        buscar_dados_cliente,
        # Crédito
        consultar_limite_credito,
        verificar_limite_pelo_score,
        solicitar_aumento_limite,
        # Câmbio
        consultar_cotacao,
        listar_moedas_suportadas,
        # Entrevista de crédito
        calcular_score_credito,
        atualizar_score_cliente,
        # Sessão
        encerrar_atendimento,
    ],
    models=[get_coordinator_model()],
    agents=[triagem_agent, credito_agent, entrevista_agent, cambio_agent],
    teams=[team],
    dbs=[PostgresDb(db_url=DB_URL)],
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
