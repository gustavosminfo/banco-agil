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

from app.routers.kapso_webhook import router as kapso_router
from banco_agil.agents import cambio_agent, credito_agent, entrevista_agent, triagem_agent
from banco_agil.config import DB_URL, get_coordinator_model
from banco_agil.team import criar_equipe, criar_equipe_factory
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

team = criar_equipe()               # singleton para Registry/Studio (metadados)
team_factory = criar_equipe_factory()  # factory para AgentOS (fresco por request)

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
    # Deve bater exatamente com o "AGENTOS ID" já registrado no projeto
    # "Banco Ágil" em os.agno.com — sem isso, o os_id é gerado de novo a
    # cada restart e o Studio aponta para uma instância desconectada.
    id="4f0a47fb-8d88-45a8-baee-d357556cb27b",
    name="Banco Ágil",
    agents=[triagem_agent, credito_agent, entrevista_agent, cambio_agent],
    teams=[team_factory],
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

# Canal WhatsApp (Kapso) — aditivo: router isolado, não toca em nenhuma rota
# do AgentOS. Ver banco_agil/channels/ para a lógica de negócio do canal.
app.include_router(kapso_router)

# API key authentication is handled natively pelo Agno via a variável de
# ambiente OS_SECURITY_KEY (lida por AgnoAPISettings). Quando definida no
# Railway, o próprio AgentOS exige Authorization: Bearer <key> em todas as
# rotas — incluindo WebSocket e endpoints internos do Studio — sem precisar
# de middleware customizado aqui.
