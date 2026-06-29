import httpx

from banco_agil.tools.exchange_tools import consultar_cotacao, listar_moedas_suportadas


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("erro", request=request, response=response)

    def json(self):
        return self._json_data


def test_consultar_cotacao_sucesso(monkeypatch):
    fake_payload = {
        "USDBRL": {
            "bid": "5.28",
            "ask": "5.30",
            "pctChange": "0.35",
            "create_date": "2026-06-27 14:22:00",
        }
    }
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None, headers=None: _FakeResponse(fake_payload))

    resultado = consultar_cotacao("dolar")

    assert resultado["par"] == "USD-BRL"
    assert resultado["compra"] == 5.28
    assert resultado["venda"] == 5.30
    assert resultado["variacao_pct"] == 0.35


def test_consultar_cotacao_aceita_codigo_iso(monkeypatch):
    fake_payload = {
        "EURBRL": {"bid": "5.7", "ask": "5.8", "pctChange": "-0.1", "create_date": "x"}
    }
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None, headers=None: _FakeResponse(fake_payload))

    resultado = consultar_cotacao("EUR")
    assert resultado["par"] == "EUR-BRL"


def test_consultar_cotacao_timeout(monkeypatch):
    def _raise_timeout(url, timeout=None, headers=None):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(httpx, "get", _raise_timeout)

    resultado = consultar_cotacao("dolar")
    assert "erro" in resultado


def test_consultar_cotacao_moeda_nao_suportada(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None, headers=None: _FakeResponse({}, status_code=404))

    resultado = consultar_cotacao("moeda_inexistente")
    assert "erro" in resultado
    assert "não encontrada" in resultado["erro"]


def test_consultar_cotacao_429_persistente_nao_confunde_com_moeda_invalida(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None, headers=None: _FakeResponse({}, status_code=429))
    monkeypatch.setattr("banco_agil.tools.exchange_tools.time.sleep", lambda s: None)

    resultado = consultar_cotacao("dolar")
    assert "erro" in resultado
    # Bug real corrigido: 429 (rate limit) não deve ser reportado como
    # "moeda não suportada" — induzia o agente a uma resposta enganosa.
    assert "não encontrada" not in resultado["erro"]
    assert "limite de requisições" in resultado["erro"].lower()


def test_consultar_cotacao_429_recupera_na_segunda_tentativa(monkeypatch):
    fake_payload = {
        "USDBRL": {"bid": "5.28", "ask": "5.30", "pctChange": "0.35", "create_date": "x"}
    }
    respostas = [_FakeResponse({}, status_code=429), _FakeResponse(fake_payload)]
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None, headers=None: respostas.pop(0))
    monkeypatch.setattr("banco_agil.tools.exchange_tools.time.sleep", lambda s: None)

    resultado = consultar_cotacao("dolar")
    assert "erro" not in resultado
    assert resultado["compra"] == 5.28


def test_consultar_cotacao_resposta_inesperada(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None, headers=None: _FakeResponse({"OUTRACHAVE": {}}))

    resultado = consultar_cotacao("dolar")
    assert "erro" in resultado


def test_listar_moedas_suportadas():
    moedas = listar_moedas_suportadas()
    assert "USD-BRL" in moedas
    assert "EUR-BRL" in moedas
    assert moedas == sorted(moedas)
