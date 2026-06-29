"""
banco_agil/tools/exchange_tools.py
Ferramentas do Agente de Câmbio.
Utiliza a AwesomeAPI para cotações em tempo real.
API: https://economia.awesomeapi.com.br/json/last/{par}
"""

import time

import httpx
from banco_agil.config import AWESOMEAPI_TOKEN, CAMBIO_API_URL, MOEDA_PARA_PAR

_MAX_TENTATIVAS_429 = 2
_ESPERA_ENTRE_TENTATIVAS_429 = 1.5  # segundos


def consultar_cotacao(moeda: str) -> dict:
    """
    Consulta a cotação atual de uma moeda em relação ao Real (BRL).

    Args:
        moeda: Nome da moeda em português ou código ISO.
               Exemplos: "dolar", "euro", "libra", "bitcoin", "USD", "EUR".

    Returns:
        dict com {moeda, par, compra, venda, variacao_pct, timestamp, fonte}
        ou {erro} em caso de falha.
    """
    moeda_norm = moeda.lower().strip()
    par        = MOEDA_PARA_PAR.get(moeda_norm, f"{moeda.upper()}-BRL")

    url = CAMBIO_API_URL.format(pair=par)
    headers = {"x-api-key": AWESOMEAPI_TOKEN} if AWESOMEAPI_TOKEN else {}

    for tentativa in range(1, _MAX_TENTATIVAS_429 + 1):
        try:
            response = httpx.get(url, headers=headers, timeout=8.0)
            response.raise_for_status()
            data = response.json()
            break
        except httpx.TimeoutException:
            return {"erro": "Serviço de cotação indisponível (timeout). Tente novamente."}
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 429 and tentativa < _MAX_TENTATIVAS_429:
                time.sleep(_ESPERA_ENTRE_TENTATIVAS_429)
                continue
            if status == 429:
                return {"erro": "Serviço de cotação temporariamente sobrecarregado (limite de requisições excedido). Tente novamente em alguns instantes."}
            if status == 404:
                return {"erro": f"Moeda '{moeda}' não encontrada ou não suportada. (par {par})"}
            return {"erro": f"Serviço de cotação retornou erro inesperado ({status}). Tente novamente."}
        except Exception as exc:
            return {"erro": f"Erro ao consultar cotação: {exc}"}

    # A AwesomeAPI retorna uma chave dinâmica no formato "USDBRL", "EURBRL", etc.
    chave = par.replace("-", "")
    if chave not in data:
        return {"erro": f"Resposta inesperada para o par {par}."}

    cotacao = data[chave]

    return {
        "moeda":         moeda.upper(),
        "par":           par,
        "compra":        float(cotacao.get("bid", 0)),
        "venda":         float(cotacao.get("ask", 0)),
        "variacao_pct":  float(cotacao.get("pctChange", 0)),
        "timestamp":     cotacao.get("create_date", "N/D"),
        "fonte":         "AwesomeAPI (economia.awesomeapi.com.br)",
    }


def listar_moedas_suportadas() -> list[str]:
    """Retorna a lista de moedas configuradas no sistema."""
    return sorted(set(MOEDA_PARA_PAR.values()))
