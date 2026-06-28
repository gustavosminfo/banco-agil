"""
banco_agil/team.py
Equipe principal do Banco Ágil — compatível com Agno 2.6+, AgentOS.

Arquitetura:
  - mode="coordinate": o coordenador mantém contexto e decide qual agente acionar.
  - session_state: persiste autenticação e dados do cliente entre turnos.
  - AsyncPostgresDb: sessão/tracing sobrevivem a restarts; storage compartilhado
    entre instâncias do AgentOS (runtime stateless). Usamos a variante
    assíncrona porque o AgentOS roda num event loop async (FastAPI) — um
    PostgresDb síncrono bloqueia o worker inteiro na primeira escrita real.
  - Transições entre agentes são imperceptíveis ao cliente.
"""

import re
from typing import Optional

import banco_agil._agno_patches  # noqa: F401 — aplica patches antes de usar AsyncPostgresDb

from agno.team import Team
from agno.team.mode import TeamMode
from agno.db.postgres import AsyncPostgresDb

from banco_agil.config import DB_URL, MAX_AUTH_ATTEMPTS, get_coordinator_model
from banco_agil.agents import (
    triagem_agent,
    credito_agent,
    entrevista_agent,
    cambio_agent,
)


# ── Estado inicial da sessão ──────────────────────────────────────────────────

_INITIAL_SESSION_STATE = {
    "autenticado": False,
    "cpf": None,
    "nome": None,
    "score": None,
    "limite_credito": None,
    "tentativas_auth": 0,
    "agente_ativo": "triagem",  # triagem | credito | entrevista | cambio
    "encerrado": False,
}


# ── Fábrica da equipe ─────────────────────────────────────────────────────────

def criar_equipe() -> Team:
    """
    Cria e retorna a equipe (Team) do Banco Ágil registrada no AgentOS.

    O AgentOS resolve a sessão (session_id) por requisição via API — o estado
    inicial abaixo é aplicado automaticamente pelo Agno na primeira mensagem
    de cada sessão nova.
    """
    return Team(
        id="banco-agil",
        name="Banco Ágil",
        mode=TeamMode.coordinate,
        model=get_coordinator_model(),
        members=[triagem_agent, credito_agent, entrevista_agent, cambio_agent],
        session_state=_INITIAL_SESSION_STATE.copy(),
        db=AsyncPostgresDb(db_url=DB_URL),
        add_history_to_context=True,
        add_session_state_to_context=True,
        num_history_runs=10,
        instructions=[
            # ── Identidade ───────────────────────────────────────────────────
            "Você coordena o atendimento do Banco Ágil.",
            "Para o cliente, existe um único atendente — nunca mencione 'equipe' ou 'agentes'.",
            "Mantenha tom cordial, profissional e objetivo em toda a conversa.",

            # ── Controle de autenticação ──────────────────────────────────────
            "SEMPRE verifique session_state['autenticado'] antes de qualquer ação.",

            "Se session_state['autenticado'] == False:",
            f"  - Se session_state['tentativas_auth'] >= {MAX_AUTH_ATTEMPTS}:",
            "      Encerre o atendimento educadamente: 'Por segurança, o acesso foi bloqueado",
            "      após 3 tentativas. Entre em contato com nossa Central: 0800 000 0000.'",
            "      Defina session_state['encerrado'] = True.",
            "  - Caso contrário: delegue ao Agente de Triagem.",

            "Se session_state['autenticado'] == True:",
            "  - Delegue conforme a necessidade identificada (crédito, câmbio, entrevista).",
            "  - Garanta que o CPF do cliente seja passado nos contextos das ferramentas.",

            # ── Processamento de tags ocultas ─────────────────────────────────
            "Ao receber resposta de um agente membro, processe as tags ocultas antes",
            "de repassar a resposta ao cliente (remova as tags da mensagem final):",

            "  [AUTH_OK|cpf=X|nome=Y|score=Z|limite=W]:",
            "    → session_state['autenticado'] = True",
            "    → session_state['cpf'] = X",
            "    → session_state['nome'] = Y",
            "    → session_state['score'] = Z",
            "    → session_state['limite_credito'] = W",
            "    → session_state['tentativas_auth'] = 0",

            "  [AUTH_FAIL]:",
            "    → session_state['tentativas_auth'] += 1",

            "  [ROUTE|credito]:",
            "    → session_state['agente_ativo'] = 'credito'",
            "    → delegue ao Agente de Crédito na próxima mensagem",

            "  [ROUTE|entrevista]:",
            "    → session_state['agente_ativo'] = 'entrevista'",
            "    → delegue ao Agente de Entrevista de Crédito",

            "  [ROUTE|credito|score_atualizado=X]:",
            "    → session_state['agente_ativo'] = 'credito'",
            "    → session_state['score'] = X",
            "    → delegue ao Agente de Crédito informando o score atualizado",

            "  [ROUTE|cambio]:",
            "    → session_state['agente_ativo'] = 'cambio'",
            "    → delegue ao Agente de Câmbio",

            # ── Encerramento voluntário ───────────────────────────────────────
            "Se o cliente pedir para encerrar/sair/finalizar:",
            "  - Despeça-se cordialmente e defina session_state['encerrado'] = True.",

            # ── Regras gerais ─────────────────────────────────────────────────
            "Nunca mostre tags, metadados ou detalhes técnicos ao cliente.",
            "Nunca invente dados — sempre use as ferramentas para obter informações reais.",
            "Em caso de erro de ferramenta, informe o cliente e ofereça alternativas.",
        ],
        show_members_responses=False,
        markdown=True,
    )


# ── Helpers de processamento de resposta ──────────────────────────────────────

_TAG_PATTERN = re.compile(
    r"\[(AUTH_OK[^\]]*|AUTH_FAIL|ROUTE\|[^\]]*)\]",
    re.IGNORECASE,
)


def limpar_tags_da_resposta(texto: str) -> str:
    """Remove tags ocultas do texto antes de exibir ao cliente."""
    return _TAG_PATTERN.sub("", texto).strip()


def extrair_info_auth(texto: str) -> Optional[dict]:
    """
    Extrai dados de autenticação da tag [AUTH_OK|cpf=...|nome=...|score=...|limite=...].
    Retorna None se a tag não estiver presente.
    """
    m = re.search(
        r"\[AUTH_OK\|cpf=(?P<cpf>[^\|]+)\|nome=(?P<nome>[^\|]+)"
        r"\|score=(?P<score>[^\|]+)\|limite=(?P<limite>[^\]]+)\]",
        texto,
        re.IGNORECASE,
    )
    if not m:
        return None
    return {
        "cpf": m.group("cpf").strip(),
        "nome": m.group("nome").strip(),
        "score": int(m.group("score").strip()),
        "limite_credito": float(m.group("limite").strip()),
    }
