from banco_agil.tools.auth_tools import autenticar_cliente, buscar_dados_cliente


def test_autenticar_cliente_sucesso(isolated_csvs):
    resultado = autenticar_cliente("123.456.789-01", "15/05/1990")

    assert resultado["sucesso"] is True
    assert resultado["dados_cliente"]["nome"] == "Ana Oliveira"
    assert resultado["dados_cliente"]["score"] == 720
    assert resultado["dados_cliente"]["limite_credito"] == 5000.0


def test_autenticar_cliente_aceita_data_iso(isolated_csvs):
    resultado = autenticar_cliente("12345678901", "1990-05-15")
    assert resultado["sucesso"] is True


def test_autenticar_cliente_cpf_invalido(isolated_csvs):
    resultado = autenticar_cliente("123", "15/05/1990")

    assert resultado["sucesso"] is False
    assert resultado["dados_cliente"] is None
    assert "inválido" in resultado["mensagem"].lower()


def test_autenticar_cliente_nao_encontrado(isolated_csvs):
    resultado = autenticar_cliente("00000000000", "01/01/2000")

    assert resultado["sucesso"] is False
    assert resultado["dados_cliente"] is None


def test_autenticar_cliente_data_nao_confere(isolated_csvs):
    resultado = autenticar_cliente("12345678901", "01/01/2000")

    assert resultado["sucesso"] is False
    assert "não conferem" in resultado["mensagem"].lower()


def test_buscar_dados_cliente_encontrado(isolated_csvs):
    dados = buscar_dados_cliente("98765432100")

    assert dados is not None
    assert dados["nome"] == "Bruno Santos"
    assert dados["score"] == 450


def test_buscar_dados_cliente_nao_encontrado(isolated_csvs):
    assert buscar_dados_cliente("00000000000") is None
