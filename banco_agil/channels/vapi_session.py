"""
banco_agil/channels/vapi_session.py
Estado de sessão por ligação (call_id) para o canal VAPI.AI.

A VAPI não fala com o Agno — cada tool-call é uma requisição HTTP isolada e
stateless, sem persistência automática de estado entre chamadas (diferente
do Team, que carrega/persiste session_state via PostgresDb a cada
Team.arun()). Para reaproveitar as funções de banco_agil/tools/*.py sem
alterá-las, construímos aqui um `agno.run.RunContext` real (não um adapter
duck-typed): `encerrar_atendimento` (banco_agil/tools/session_tools.py) é
decorada com `@tool(...)` do Agno, que valida o tipo de `run_context` via
Pydantic em tempo de chamada — um objeto apenas com `.session_state` (sem
ser literalmente um `RunContext`) é rejeitado por essa validação estrita.
As demais tools (auth_tools, credit_tools, interview_tools) são funções
Python simples, sem essa validação, mas também aceitam um `RunContext` real
normalmente — usar o tipo real em todos os casos evita dois caminhos
diferentes.

Autorização é sempre resolvida a partir do valor lido do Postgres nesta
chamada — nunca de um objeto reaproveitado em memória entre requisições.
Esse é o mesmo princípio que corrigiu o bug real do canal WhatsApp
(team.session_state, congelado no valor inicial do construtor, vs
run_context.session_state, que reflete o estado realmente persistido — ver
credit_tools._verificar_autorizacao). Aqui a situação é ainda mais direta:
não existe nem chance de reaproveitar um objeto Team em memória, porque a
sessão é recriada do zero (leitura no Postgres) a cada webhook.
"""

import json
import logging

import psycopg
from agno.run import RunContext

from banco_agil.config import DB_URL

logger = logging.getLogger(__name__)

# Mesmas chaves/valores default do Team (banco_agil/team.py::_INITIAL_SESSION_STATE)
# — mantém as mesmas regras de negócio (MAX_AUTH_ATTEMPTS etc.) entre canais.
_INITIAL_SESSION_STATE = {
    "autenticado": False,
    "cpf": None,
    "nome": None,
    "score": None,
    "limite_credito": None,
    "tentativas_auth": 0,
    "agente_ativo": "triagem",
    "encerrado": False,
}


def _dsn_psycopg(db_url: str) -> str:
    """Converte a URL no dialeto SQLAlchemy (postgresql+psycopg://) para o
    DSN puro que psycopg.connect() espera (postgresql://)."""
    return db_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _garantir_tabela(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vapi_call_sessions (
            call_id       TEXT PRIMARY KEY,
            session_state JSONB NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.commit()


def carregar_run_context(call_id: str) -> RunContext:
    """Carrega o session_state persistido para esta ligação (ou cria um novo,
    estado inicial, se for a primeira tool-call dessa ligação) e devolve um
    RunContext real pronto para ser passado às tools existentes.

    `run_id` e `session_id` usam o próprio call_id da VAPI — não há conceito
    de "run" separado aqui (cada tool-call já é processada de forma
    independente), só precisamos de um RunContext válido para carregar
    session_state.
    """
    dsn = _dsn_psycopg(DB_URL)
    with psycopg.connect(dsn) as conn:
        _garantir_tabela(conn)
        cur = conn.execute(
            "SELECT session_state FROM vapi_call_sessions WHERE call_id = %s",
            (call_id,),
        )
        linha = cur.fetchone()
        session_state = linha[0] if linha is not None else _INITIAL_SESSION_STATE.copy()

    return RunContext(run_id=call_id, session_id=call_id, session_state=session_state)


def salvar_run_context(call_id: str, run_context: RunContext) -> None:
    dsn = _dsn_psycopg(DB_URL)
    with psycopg.connect(dsn) as conn:
        _garantir_tabela(conn)
        conn.execute(
            """
            INSERT INTO vapi_call_sessions (call_id, session_state, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (call_id) DO UPDATE
                SET session_state = EXCLUDED.session_state,
                    updated_at = now()
            """,
            (call_id, json.dumps(run_context.session_state)),
        )
        conn.commit()


def encerrar_sessao(call_id: str) -> None:
    """Remove a sessão da ligação ao término da chamada — CPF e nome não
    precisam ser retidos após o encerramento (minimização de dado sensível,
    mesma postura já usada no restante do projeto)."""
    dsn = _dsn_psycopg(DB_URL)
    try:
        with psycopg.connect(dsn) as conn:
            _garantir_tabela(conn)
            conn.execute("DELETE FROM vapi_call_sessions WHERE call_id = %s", (call_id,))
            conn.commit()
    except Exception:
        logger.exception("Falha ao limpar sessão de ligação (call_id=%s).", call_id)
