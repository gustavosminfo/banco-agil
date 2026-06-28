import pandas as pd

from banco_agil.tools.credit_tools import (
    consultar_limite_credito,
    verificar_limite_pelo_score,
    solicitar_aumento_limite,
)


def test_consultar_limite_credito_sucesso(isolated_csvs):
    resultado = consultar_limite_credito("12345678901")

    assert resultado["nome"] == "Ana Oliveira"
    assert resultado["score"] == 720
    assert resultado["limite_atual"] == 5000.0


def test_consultar_limite_credito_nao_encontrado(isolated_csvs):
    resultado = consultar_limite_credito("00000000000")
    assert "erro" in resultado


def test_verificar_limite_pelo_score_elegivel():
    resultado = verificar_limite_pelo_score(720, 9000)
    assert resultado["elegivel"] is True
    assert resultado["limite_maximo_permitido"] == 10000.0
    assert resultado["faixa_score"] == "700-799"


def test_verificar_limite_pelo_score_nao_elegivel():
    resultado = verificar_limite_pelo_score(450, 5000)
    assert resultado["elegivel"] is False
    assert resultado["limite_maximo_permitido"] == 2000.0


def test_verificar_limite_pelo_score_borda_superior():
    # Score 799 deve cair na faixa 700-799, não na 800-1000.
    resultado = verificar_limite_pelo_score(799, 10000)
    assert resultado["faixa_score"] == "700-799"
    assert resultado["elegivel"] is True


def test_verificar_limite_pelo_score_fora_dos_parametros():
    resultado = verificar_limite_pelo_score(1500, 1000)
    assert resultado["elegivel"] is False
    assert "erro" in resultado


def test_solicitar_aumento_limite_aprovado(isolated_csvs):
    # Ana: score 720 -> limite máximo permitido R$ 10.000.
    resultado = solicitar_aumento_limite("12345678901", 9000)

    assert resultado["status"] == "aprovado"
    assert resultado["novo_limite_solicitado"] == 9000

    # Limite deve ter sido persistido em clientes.csv.
    novo = consultar_limite_credito("12345678901")
    assert novo["limite_atual"] == 9000

    # Solicitação deve ter sido registrada.
    df_sol = pd.read_csv(isolated_csvs["solicitacoes"])
    assert len(df_sol) == 1
    assert df_sol.iloc[0]["status_pedido"] == "aprovado"


def test_solicitar_aumento_limite_rejeitado_por_score(isolated_csvs):
    # Bruno: score 450 -> limite máximo permitido R$ 2.000.
    resultado = solicitar_aumento_limite("98765432100", 5000)

    assert resultado["status"] == "rejeitado"
    # Limite não deve ter sido alterado.
    assert consultar_limite_credito("98765432100")["limite_atual"] == 1500.0


def test_solicitar_aumento_limite_valor_menor_que_atual(isolated_csvs):
    resultado = solicitar_aumento_limite("12345678901", 1000)
    assert resultado["status"] == "rejeitado"


def test_solicitar_aumento_limite_cliente_inexistente(isolated_csvs):
    resultado = solicitar_aumento_limite("00000000000", 5000)
    assert resultado["status"] == "erro"
