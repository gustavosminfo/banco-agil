"""
banco_agil/_agno_patches.py
Correções locais para bugs conhecidos e ainda não mergeados no Agno 2.6.x.

Bug: `agno.db.postgres.{postgres,async_postgres}` registram as tabelas na
`MetaData` do SQLAlchemy sem `extend_existing=True`. Quando duas corrotinas
tentam criar a mesma tabela quase simultaneamente (ex.: o coordenador do
Team e os agentes membros acessando a sessão na primeira mensagem), a
segunda chamada lança `InvalidRequestError: Table 'X' is already defined
for this MetaData instance` — e o retry subsequente trava o request.

Referências (PRs da comunidade com a mesma correção, fechadas sem merge):
  - https://github.com/agno-agi/agno/issues/7319
  - https://github.com/agno-agi/agno/pull/7322
  - https://github.com/agno-agi/agno/pull/7334

Remover este patch quando uma versão futura do Agno incluir a correção
oficialmente (conferir se `extend_existing=True` já aparece nativamente em
`agno/db/postgres/postgres.py` e `async_postgres.py`).
"""

from sqlalchemy import Table as _SATable

import agno.db.postgres.async_postgres as _async_postgres_mod
import agno.db.postgres.postgres as _sync_postgres_mod


def _table_com_extend_existing(*args, **kwargs):
    kwargs.setdefault("extend_existing", True)
    return _SATable(*args, **kwargs)


_async_postgres_mod.Table = _table_com_extend_existing  # type: ignore[assignment,misc]
_sync_postgres_mod.Table = _table_com_extend_existing  # type: ignore[assignment,misc]
