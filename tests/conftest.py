"""
tests/conftest.py
Fixtures compartilhadas — isolam os testes dos CSVs reais em data/,
copiando-os para um diretório temporário antes de cada teste que mexe
em arquivo (evita corromper data/clientes.csv durante a suíte).
"""

import shutil

import pytest

from banco_agil.config import CLIENTES_CSV, SCORE_LIMITE_CSV

from banco_agil.tools import auth_tools, credit_tools, interview_tools


@pytest.fixture
def isolated_csvs(tmp_path, monkeypatch):
    """Copia clientes.csv e score_limite.csv para tmp_path e repatcheia os
    módulos de tools para usarem essas cópias, em vez dos arquivos reais."""
    clientes_tmp = tmp_path / "clientes.csv"
    score_tmp = tmp_path / "score_limite.csv"
    solicitacoes_tmp = tmp_path / "solicitacoes_aumento_limite.csv"

    shutil.copy(CLIENTES_CSV, clientes_tmp)
    shutil.copy(SCORE_LIMITE_CSV, score_tmp)

    for module in (auth_tools, credit_tools, interview_tools):
        if hasattr(module, "CLIENTES_CSV"):
            monkeypatch.setattr(module, "CLIENTES_CSV", clientes_tmp)
    monkeypatch.setattr(credit_tools, "SCORE_LIMITE_CSV", score_tmp)
    monkeypatch.setattr(credit_tools, "SOLICITACOES_CSV", solicitacoes_tmp)

    return {
        "clientes": clientes_tmp,
        "score_limite": score_tmp,
        "solicitacoes": solicitacoes_tmp,
    }
