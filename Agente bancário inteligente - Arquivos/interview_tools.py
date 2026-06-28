"""
banco_agil/tools/interview_tools.py
Ferramentas do Agente de Entrevista de Crédito.
Calcula o novo score com a fórmula ponderada do desafio e atualiza clientes.csv.
"""

from typing import Literal
import pandas as pd
from banco_agil.config import CLIENTES_CSV


# ── Pesos da fórmula de score ─────────────────────────────────────────────────

PESO_RENDA = 30

PESO_EMPREGO: dict[str, int] = {
    "formal":       300,
    "autonomo":     200,
    "autônomo":     200,
    "desempregado": 0,
}

PESO_DEPENDENTES: dict[int | str, int] = {
    0:   100,
    1:   80,
    2:   60,
    "3+": 30,
}

PESO_DIVIDAS: dict[str, int] = {
    "sim": -100,
    "nao":  100,
    "não":  100,
}


# ── Cálculo do score ──────────────────────────────────────────────────────────

def calcular_score_credito(
    renda_mensal: float,
    tipo_emprego: Literal["formal", "autonomo", "autônomo", "desempregado"],
    despesas_fixas_mensais: float,
    num_dependentes: int,
    tem_dividas: Literal["sim", "nao", "não"],
) -> dict:
    """
    Calcula o score de crédito com base em dados financeiros coletados na entrevista.

    Fórmula:
        score = (renda / (despesas + 1)) * peso_renda
                + peso_emprego[tipo_emprego]
                + peso_dependentes[num_dependentes]
                + peso_dividas[tem_dividas]

    O resultado é limitado ao intervalo [0, 1000].

    Args:
        renda_mensal:           Renda bruta mensal em R$.
        tipo_emprego:           "formal", "autonomo" / "autônomo" ou "desempregado".
        despesas_fixas_mensais: Total de despesas fixas mensais em R$.
        num_dependentes:        Número de dependentes (0, 1, 2 ou 3+).
        tem_dividas:            "sim" ou "nao" / "não".

    Returns:
        dict com {score, detalhamento} para transparência no cálculo.
    """
    tipo_emprego_norm = tipo_emprego.lower().strip()
    tem_dividas_norm  = tem_dividas.lower().strip()

    # Validação dos inputs
    if tipo_emprego_norm not in PESO_EMPREGO:
        return {
            "erro": f"Tipo de emprego inválido: '{tipo_emprego}'. "
                    "Aceitos: formal, autonomo, desempregado."
        }
    if tem_dividas_norm not in PESO_DIVIDAS:
        return {
            "erro": f"Valor inválido para tem_dividas: '{tem_dividas}'. "
                    "Aceitos: sim, nao."
        }

    # Chave de dependentes
    dep_key: int | str = num_dependentes if num_dependentes < 3 else "3+"

    # Parcelas do score
    parcela_renda       = (renda_mensal / (despesas_fixas_mensais + 1)) * PESO_RENDA
    parcela_emprego     = PESO_EMPREGO[tipo_emprego_norm]
    parcela_dependentes = PESO_DEPENDENTES.get(dep_key, 30)
    parcela_dividas     = PESO_DIVIDAS[tem_dividas_norm]

    score_bruto = (
        parcela_renda + parcela_emprego + parcela_dependentes + parcela_dividas
    )
    score_final = max(0, min(1000, round(score_bruto)))

    return {
        "score": score_final,
        "detalhamento": {
            "parcela_renda":        round(parcela_renda, 2),
            "parcela_emprego":      parcela_emprego,
            "parcela_dependentes":  parcela_dependentes,
            "parcela_dividas":      parcela_dividas,
            "score_bruto":          round(score_bruto, 2),
        },
    }


def atualizar_score_cliente(cpf: str, novo_score: int) -> dict:
    """
    Persiste o novo score do cliente em clientes.csv.

    Args:
        cpf:        CPF do cliente (apenas dígitos).
        novo_score: Score recalculado (0-1000).

    Returns:
        dict com {sucesso, score_anterior, score_novo, mensagem}.
    """
    try:
        df = pd.read_csv(CLIENTES_CSV, dtype={"cpf": str})
    except FileNotFoundError:
        return {"sucesso": False, "mensagem": "Base de clientes indisponível."}

    linha_idx = df.index[df["cpf"] == cpf].tolist()
    if not linha_idx:
        return {"sucesso": False, "mensagem": f"Cliente CPF {cpf} não encontrado."}

    score_anterior = int(df.at[linha_idx[0], "score"])
    df.at[linha_idx[0], "score"] = novo_score
    df.to_csv(CLIENTES_CSV, index=False)

    return {
        "sucesso":        True,
        "score_anterior": score_anterior,
        "score_novo":     novo_score,
        "mensagem": (
            f"Score atualizado de {score_anterior} para {novo_score}."
        ),
    }
