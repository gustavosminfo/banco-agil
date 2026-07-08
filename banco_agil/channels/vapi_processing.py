"""
banco_agil/channels/vapi_processing.py
Orquestração do canal de Ligação (VAPI.AI): despacha tool-calls recebidas via
webhook diretamente para as funções de banco_agil/tools/*.py — SEM passar
pelo Team/Agno. A VAPI já faz sua própria orquestração (modelo, prompt,
STT/TTS) fora do nosso processo; aqui só executamos a lógica de negócio real
e devolvemos o resultado no formato que a VAPI espera.

Nenhuma regra de negócio é duplicada: as mesmas funções usadas pelo
Streamlit/WhatsApp (auth_tools, credit_tools, interview_tools,
exchange_tools, session_tools) são reaproveitadas tal como estão, recebendo
um `agno.run.RunContext` real (ver vapi_session.py — `encerrar_atendimento`
é decorada com `@tool(...)` do Agno, que valida estritamente o tipo de
`run_context` via Pydantic, então não aceita um adapter duck-typed).
"""

import json
import logging
from typing import Callable

from agno.run import RunContext

from banco_agil.channels import vapi_session
from banco_agil.team import limpar_tags_da_resposta
from banco_agil.tools import auth_tools, credit_tools, exchange_tools, interview_tools
from banco_agil.tools.auth_tools import _mascarar_cpf, _normalizar_cpf
from banco_agil.tools.session_tools import encerrar_atendimento

logger = logging.getLogger(__name__)

# Tools que tocam conta/sessão — recebem a SessaoLigacao via run_context=.
_TOOLS_COM_SESSAO: dict[str, Callable] = {
    "autenticar_cliente": auth_tools.autenticar_cliente,
    "solicitar_aumento_limite": credit_tools.solicitar_aumento_limite,
    "atualizar_score_cliente": interview_tools.atualizar_score_cliente,
}

# Tools sem estado de sessão — mesma assinatura de sempre, sem run_context.
_TOOLS_SEM_SESSAO: dict[str, Callable] = {
    "buscar_dados_cliente": auth_tools.buscar_dados_cliente,
    "consultar_limite_credito": credit_tools.consultar_limite_credito,
    "verificar_limite_pelo_score": credit_tools.verificar_limite_pelo_score,
    "calcular_score_credito": interview_tools.calcular_score_credito,
    "consultar_cotacao": exchange_tools.consultar_cotacao,
    "listar_moedas_suportadas": exchange_tools.listar_moedas_suportadas,
}

# CPF é sempre normalizado (só dígitos) antes de chegar às tools — consultar_
# limite_credito, por exemplo, compara direto contra a coluna do CSV (que já
# é só dígitos), sem normalizar internamente.
_ARGS_CPF = {"cpf"}


def _normalizar_args(args: dict) -> dict:
    normalizados = dict(args)
    for chave in _ARGS_CPF:
        if chave in normalizados and isinstance(normalizados[chave], str):
            normalizados[chave] = _normalizar_cpf(normalizados[chave])
    return normalizados


def _nome_e_argumentos(chamada: dict) -> tuple[str, dict]:
    """Extrai nome e argumentos de um item de toolCallList, suportando os dois
    formatos observados: plano ({id, name, arguments}) e o formato nativo da
    OpenAI ({id, type: "function", function: {name, arguments}}), usado pela
    VAPI quando o model provider é openai/gpt-4o — nesse caso `arguments`
    também vem como STRING JSON, não como objeto. Sem esse tratamento, o
    dispatcher lia nome vazio e toda tool-call falhava com "Tool desconhecida"
    (bug real observado em produção: autenticar_cliente nunca era executada)."""
    fn = chamada.get("function")
    if fn:
        nome = fn.get("name", "")
        args_raw = fn.get("arguments", {})
    else:
        nome = chamada.get("name", "")
        args_raw = chamada.get("arguments", {})

    if isinstance(args_raw, str):
        try:
            args = json.loads(args_raw) if args_raw.strip() else {}
        except json.JSONDecodeError:
            logger.warning("arguments da tool-call não é JSON válido: %r", args_raw[:200])
            args = {}
    else:
        args = args_raw or {}

    return nome, args


def _executar_tool(nome: str, args: dict, run_context: RunContext) -> dict:
    args = _normalizar_args(args)

    if nome == "encerrar_atendimento":
        # Única tool com retorno em string (não dict) — Agno @tool nativa,
        # chamada via .entrypoint (o objeto Function do Agno não é
        # diretamente chamável). O texto vem com a tag [ENCERRADO] (usada
        # pelo canal WhatsApp para sincronizar o painel da Kapso); aqui não
        # há tag a processar, só removemos antes de devolver à VAPI.
        texto = encerrar_atendimento.entrypoint(run_context=run_context)
        return {"mensagem": limpar_tags_da_resposta(texto), "encerrado": True}

    if nome in _TOOLS_COM_SESSAO:
        return _TOOLS_COM_SESSAO[nome](**args, run_context=run_context)

    if nome in _TOOLS_SEM_SESSAO:
        return _TOOLS_SEM_SESSAO[nome](**args)

    logger.warning("Tool-call desconhecida recebida da VAPI: %r", nome)
    return {"erro": f"Tool desconhecida: {nome}"}


async def processar_tool_calls(message: dict) -> list[dict]:
    """Processa o evento `tool-calls` do webhook da VAPI e devolve a lista de
    resultados no formato esperado (`{"results": [...]}` é montado pelo
    router — aqui só devolvemos a lista)."""
    call_id = (message.get("call") or {}).get("id")
    if not call_id:
        logger.warning("Evento tool-calls sem call.id — não é possível resolver a sessão.")
        return [
            {"toolCallId": chamada.get("id", ""), "result": json.dumps({"erro": "sessão inválida"})}
            for chamada in message.get("toolCallList", [])
        ]

    run_context = vapi_session.carregar_run_context(call_id)
    resultados = []

    for chamada in message.get("toolCallList", []):
        tool_call_id = chamada.get("id", "")
        nome, args = _nome_e_argumentos(chamada)
        try:
            resultado = _executar_tool(nome, args, run_context)
        except Exception:
            cpf_no_log = _mascarar_cpf(args.get("cpf", "")) if "cpf" in args else "-"
            logger.exception("Falha ao executar tool %r da VAPI (cpf=%s).", nome, cpf_no_log)
            resultado = {"erro": "Falha técnica ao processar a solicitação. Tente novamente."}

        resultados.append({"toolCallId": tool_call_id, "result": json.dumps(resultado, ensure_ascii=False)})

    vapi_session.salvar_run_context(call_id, run_context)
    return resultados


async def processar_fim_de_chamada(message: dict) -> None:
    """Eventos `status-update` (status="ended") e `end-of-call-report` —
    limpa a sessão da ligação encerrada (minimização de dado sensível)."""
    call_id = (message.get("call") or {}).get("id")
    if not call_id:
        return
    if message.get("type") == "status-update" and message.get("status") != "ended":
        return
    vapi_session.encerrar_sessao(call_id)
    logger.info("Sessão de ligação encerrada e removida (call_id=%s).", call_id)
