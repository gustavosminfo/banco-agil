"""
banco_agil/tools/credit_tools.py
Ferramentas do Agente de Crédito.
Consulta limite, processa solicitação de aumento e verifica elegibilidade via score.
"""

from datetime import datetime, timezone
from typing import Literal
import pandas as pd
from banco_agil.config import CLIENTES_CSV, SCORE_LIMITE_CSV, SOLICITACOES_CSV


# ── Consulta de limite ────────────────────────────────────────────────────────

def consultar_limite_credito(cpf: str) -> dict:
    """
    Retorna o limite de crédito atual e o score do cliente.

    Args:
        cpf: CPF do cliente (apenas dígitos).

    Returns:
        dict com {limite_atual, score, nome} ou {erro}.
    """
    try:
        df = pd.read_csv(CLIENTES_CSV, dtype={"cpf": str})
    except FileNotFoundError:
        return {"erro": "Base de dados indisponível."}

    linha = df[df["cpf"] == cpf]
    if linha.empty:
        return {"erro": "Cliente não encontrado."}

    c = linha.iloc[0]
    return {
        "nome":        str(c["nome"]),
        "cpf":         cpf,
        "score":       int(c["score"]),
        "limite_atual": float(c["limite_credito"]),
    }


# ── Verificação de elegibilidade ──────────────────────────────────────────────

def verificar_limite_pelo_score(score: int, novo_limite: float) -> dict:
    """
    Verifica se o score do cliente permite o novo limite solicitado.

    Args:
        score: Score atual do cliente (0-1000).
        novo_limite: Novo limite solicitado em R$.

    Returns:
        dict com {elegivel, limite_maximo_permitido, faixa_score}.
    """
    try:
        df = pd.read_csv(SCORE_LIMITE_CSV)
    except FileNotFoundError:
        return {"elegivel": False, "erro": "Tabela de score indisponível."}

    faixa = df[(df["score_minimo"] <= score) & (df["score_maximo"] >= score)]
    if faixa.empty:
        return {"elegivel": False, "erro": f"Score {score} fora dos parâmetros."}

    limite_maximo = float(faixa.iloc[0]["limite_maximo"])
    return {
        "elegivel":              novo_limite <= limite_maximo,
        "limite_maximo_permitido": limite_maximo,
        "faixa_score":           f"{int(faixa.iloc[0]['score_minimo'])}-{int(faixa.iloc[0]['score_maximo'])}",
    }


# ── Processamento de solicitação ──────────────────────────────────────────────

def solicitar_aumento_limite(cpf: str, novo_limite: float) -> dict:
    """
    Cria um registro de solicitação de aumento de limite e aprova/rejeita
    com base no score atual do cliente.

    Grava em solicitacoes_aumento_limite.csv com as colunas:
        cpf_cliente | data_hora_solicitacao | limite_atual | novo_limite_solicitado | status_pedido

    Args:
        cpf: CPF do cliente (apenas dígitos).
        novo_limite: Novo limite desejado em R$.

    Returns:
        dict com {status, limite_atual, novo_limite_solicitado, limite_maximo_permitido, mensagem}.
    """
    # 1. Buscar dados atuais do cliente
    dados = consultar_limite_credito(cpf)
    if "erro" in dados:
        return {"status": "erro", "mensagem": dados["erro"]}

    limite_atual = dados["limite_atual"]
    score        = dados["score"]

    # 2. Validação básica: novo limite deve ser maior que o atual
    if novo_limite <= limite_atual:
        return {
            "status": "rejeitado",
            "mensagem": (
                f"O valor solicitado (R$ {novo_limite:,.2f}) deve ser superior "
                f"ao limite atual (R$ {limite_atual:,.2f})."
            ),
            "limite_atual": limite_atual,
            "novo_limite_solicitado": novo_limite,
        }

    # 3. Verificar elegibilidade pelo score
    elegibilidade = verificar_limite_pelo_score(score, novo_limite)
    if "erro" in elegibilidade:
        return {"status": "erro", "mensagem": elegibilidade["erro"]}

    status: Literal["aprovado", "rejeitado"] = (
        "aprovado" if elegibilidade["elegivel"] else "rejeitado"
    )

    # 4. Gravar solicitação no CSV
    nova_linha = {
        "cpf_cliente":            cpf,
        "data_hora_solicitacao":  datetime.now(timezone.utc).isoformat(),
        "limite_atual":           limite_atual,
        "novo_limite_solicitado": novo_limite,
        "status_pedido":          status,
    }

    try:
        try:
            df_sol = pd.read_csv(SOLICITACOES_CSV)
        except FileNotFoundError:
            df_sol = pd.DataFrame(columns=nova_linha.keys())

        df_sol = pd.concat(
            [df_sol, pd.DataFrame([nova_linha])],
            ignore_index=True,
        )
        df_sol.to_csv(SOLICITACOES_CSV, index=False)
    except Exception as exc:
        return {"status": "erro", "mensagem": f"Erro ao gravar solicitação: {exc}"}

    # 5. Se aprovado, atualizar o limite na base de clientes
    if status == "aprovado":
        _atualizar_limite_no_csv(cpf, novo_limite)

    return {
        "status":                  status,
        "limite_atual":            limite_atual,
        "novo_limite_solicitado":  novo_limite,
        "limite_maximo_permitido": elegibilidade["limite_maximo_permitido"],
        "score":                   score,
        "mensagem": (
            f"Solicitação {status}. "
            + (
                f"Seu novo limite é R$ {novo_limite:,.2f}."
                if status == "aprovado"
                else (
                    f"Seu score atual ({score}) permite limite de até "
                    f"R$ {elegibilidade['limite_maximo_permitido']:,.2f}."
                )
            )
        ),
    }


# ── Helpers internos ──────────────────────────────────────────────────────────

def _atualizar_limite_no_csv(cpf: str, novo_limite: float) -> None:
    """Atualiza o limite_credito de um cliente na base clientes.csv."""
    df = pd.read_csv(CLIENTES_CSV, dtype={"cpf": str})
    df.loc[df["cpf"] == cpf, "limite_credito"] = novo_limite
    df.to_csv(CLIENTES_CSV, index=False)
