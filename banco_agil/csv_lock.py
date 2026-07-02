"""
banco_agil/csv_lock.py
Lock compartilhado por caminho de arquivo, para serializar leitura+escrita
de CSVs compartilhados entre múltiplas tools (ex.: clientes.csv é escrito
tanto por credit_tools.py quanto por interview_tools.py).

Sem isso, duas escritas concorrentes no mesmo arquivo (ex.: cliente
recalcula o score via entrevista e, em seguida, solicita aumento de limite,
gerando duas BackgroundTasks do canal WhatsApp em sobreposição) podem
resultar em uma leitura no meio de uma escrita incompleta — pandas lança
uma exceção de parsing que, se não tratada no ponto de chamada, propaga
silenciosamente (sem log visível em nível INFO) e o cliente só vê um
"erro técnico" genérico.
"""

import threading
from pathlib import Path

_locks: dict[Path, threading.Lock] = {}
_locks_guard = threading.Lock()


def lock_para(caminho: Path) -> threading.Lock:
    """Retorna (criando se necessário) o lock associado a um caminho de arquivo."""
    with _locks_guard:
        if caminho not in _locks:
            _locks[caminho] = threading.Lock()
        return _locks[caminho]
