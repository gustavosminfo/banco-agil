from banco_agil.tools.interview_tools import (
    calcular_score_credito,
    atualizar_score_cliente,
)


def test_calcular_score_credito_exemplo_sdd():
    # Exemplo do SDD §3 REQ-F-003: renda 5000, formal, despesas 1500,
    # 1 dependente, sem dívidas -> score ≈ 580.
    resultado = calcular_score_credito(
        renda_mensal=5000,
        tipo_emprego="formal",
        despesas_fixas_mensais=1500,
        num_dependentes=1,
        tem_dividas="nao",
    )

    assert resultado["score"] == 580


def test_calcular_score_credito_clamp_maximo():
    resultado = calcular_score_credito(
        renda_mensal=1_000_000,
        tipo_emprego="formal",
        despesas_fixas_mensais=1,
        num_dependentes=0,
        tem_dividas="nao",
    )
    assert resultado["score"] == 1000


def test_calcular_score_credito_clamp_minimo():
    resultado = calcular_score_credito(
        renda_mensal=0,
        tipo_emprego="desempregado",
        despesas_fixas_mensais=10000,
        num_dependentes=5,
        tem_dividas="sim",
    )
    assert resultado["score"] == 0


def test_calcular_score_credito_dependentes_3_ou_mais():
    resultado = calcular_score_credito(
        renda_mensal=3000,
        tipo_emprego="autonomo",
        despesas_fixas_mensais=1000,
        num_dependentes=4,
        tem_dividas="nao",
    )
    assert resultado["detalhamento"]["parcela_dependentes"] == 30


def test_calcular_score_credito_tipo_emprego_invalido():
    resultado = calcular_score_credito(
        renda_mensal=3000,
        tipo_emprego="bico",
        despesas_fixas_mensais=1000,
        num_dependentes=1,
        tem_dividas="nao",
    )
    assert "erro" in resultado


def test_calcular_score_credito_tem_dividas_invalido():
    resultado = calcular_score_credito(
        renda_mensal=3000,
        tipo_emprego="formal",
        despesas_fixas_mensais=1000,
        num_dependentes=1,
        tem_dividas="talvez",
    )
    assert "erro" in resultado


def test_atualizar_score_cliente_sucesso(isolated_csvs):
    resultado = atualizar_score_cliente("12345678901", 850)

    assert resultado["sucesso"] is True
    assert resultado["score_anterior"] == 720
    assert resultado["score_novo"] == 850


def test_atualizar_score_cliente_nao_encontrado(isolated_csvs):
    resultado = atualizar_score_cliente("00000000000", 500)
    assert resultado["sucesso"] is False
