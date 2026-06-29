"""
banco_agil/tools/session_tools.py
Ferramenta de controle de sessão do Team coordinator.
"""

from agno.run import RunContext
from agno.tools import tool


@tool(stop_after_tool_call=True)
def encerrar_atendimento(run_context: RunContext) -> str:
    """
    Encerra o atendimento a pedido do cliente, finalizando o loop de execução.

    Chame esta ferramenta sempre que o cliente pedir explicitamente para
    terminar, sair ou finalizar a conversa — em qualquer momento do
    atendimento, autenticado ou não.

    Returns:
        Mensagem de despedida a ser exibida ao cliente.
    """
    if run_context.session_state is None:
        run_context.session_state = {}
    run_context.session_state["encerrado"] = True

    return (
        "Atendimento encerrado a seu pedido. Agradecemos o contato com o "
        "Banco Ágil — tenha um excelente dia! 😊\n\n[ENCERRADO]"
    )
