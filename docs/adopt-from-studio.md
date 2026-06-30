# Adotar componentes do Studio no código (GitHub como fonte da verdade)

Você vai exportar Agents, Teams e Workflows criados no Studio (os.agno.com) para código Python,
registrá-los no repositório e configurar o ADLC para que o GitHub assuma a governança. Funciona
para projetos novos e para integrar ao projeto banco-agil existente.

---

## Passo 1 — Entender o contexto

Pergunte ao usuário:

1. **Tipo de projeto:**
   - (A) **Projeto existente** (banco-agil) — incorporar componentes Studio ao código atual
   - (B) **Projeto novo** — criar estrutura do zero baseada nos componentes Studio

2. **Origem dos dados:** os componentes Studio estão em qual banco?
   - Local (Docker): usa `DB_URL` do `.env`
   - Railway (produção): usa `EVAL_DB_URL` do `.env` (URL pública do Postgres)

3. **Quais componentes adotar?** Liste ou pergunte:
   - Todos os componentes Studio que ainda não estão em código
   - Ou componentes específicos por nome

Não prossiga sem ter clareza sobre os três pontos acima.

---

## Passo 2 — Descobrir os componentes Studio

Escreva e execute o script de descoberta abaixo. Ele conecta ao banco, lista todos os agentes,
teams e workflows armazenados, e compara com o que já existe em código.

```python
# scripts/studio_export.py  (temporário — deletar após uso)
"""Exporta componentes Studio para inspeção."""

import json
import sys
from pathlib import Path

# Garante que o projeto está no path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from banco_agil.config import DB_URL, EVAL_DB_URL
from agno.db.postgres import PostgresDb

# Escolha o banco (local ou Railway)
USE_REMOTE = "--remote" in sys.argv
db_url = EVAL_DB_URL if (USE_REMOTE and EVAL_DB_URL) else DB_URL
db = PostgresDb(db_url=db_url)

print(f"\n{'='*60}")
print(f"Banco: {'Railway (remoto)' if USE_REMOTE and EVAL_DB_URL else 'Local'}")
print(f"URL:   {db_url[:40]}...")
print(f"{'='*60}\n")

# ── Agents ────────────────────────────────────────────────────
try:
    from agno.agent.agent import get_agents
    agents = get_agents(db=db) or []
    print(f"AGENTS ({len(agents)} encontrados):")
    for a in agents:
        config = a.to_dict()
        tools  = [t.get("class_path", t.get("name", "?")) for t in config.get("tools", [])]
        model  = config.get("model", {})
        print(f"  id={a.agent_id!r:40} name={a.name!r}")
        print(f"    model: provider={model.get('provider')} id={model.get('model_id')}")
        print(f"    tools: {tools}")
        print()
except Exception as e:
    print(f"  [ERRO agents] {e}\n")

# ── Teams ─────────────────────────────────────────────────────
try:
    from agno.team.team import get_teams
    teams = get_teams(db=db) or []
    print(f"TEAMS ({len(teams)} encontrados):")
    for t in teams:
        config  = t.to_dict()
        members = [m.get("name", "?") for m in config.get("members", [])]
        print(f"  id={t.team_id!r:40} name={t.name!r}")
        print(f"    mode:    {config.get('mode')}")
        print(f"    members: {members}")
        print()
except Exception as e:
    print(f"  [ERRO teams] {e}\n")

# ── Workflows ─────────────────────────────────────────────────
try:
    from agno.workflow.workflow import get_workflows
    workflows = get_workflows(db=db) or []
    print(f"WORKFLOWS ({len(workflows)} encontrados):")
    for w in workflows:
        config = w.to_dict()
        steps  = [s.get("name", "?") for s in config.get("steps", [])]
        print(f"  id={w.workflow_id!r:40} name={w.name!r}")
        print(f"    steps: {steps}")
        print()
except Exception as e:
    print(f"  [ERRO workflows] {e}\n")
```

Execute:
```bash
# Banco local
source .venv/bin/activate
python scripts/studio_export.py

# Banco Railway (produção)
python scripts/studio_export.py --remote
```

Leia a saída completa antes de prosseguir.

---

## Passo 3 — Identificar o que ainda não está em código

Compare a lista do Passo 2 com o que já existe:

**Agentes em código:** `banco_agil/agents/*.py` (exclua `__init__.py`)
**Teams em código:** `banco_agil/team.py`
**Workflows em código:** `banco_agil/workflows/*.py` (se a pasta existir)

Monte uma lista de componentes "Studio-only" (existem no banco, não estão em código).
Apresente essa lista ao usuário e confirme quais devem ser adotados antes de prosseguir.

---

## Passo 4 — Mapear class_paths para imports

Para cada componente Studio-only, o `to_dict()` contém `class_path` de tools e modelo.
Mapeie cada um para o import Python correto:

### Tools

| class_path no dict | Import Python |
|---|---|
| `banco_agil.tools.auth_tools.<fn>` | `from banco_agil.tools.auth_tools import <fn>` |
| `banco_agil.tools.credit_tools.<fn>` | `from banco_agil.tools.credit_tools import <fn>` |
| `banco_agil.tools.exchange_tools.<fn>` | `from banco_agil.tools.exchange_tools import <fn>` |
| `banco_agil.tools.interview_tools.<fn>` | `from banco_agil.tools.interview_tools import <fn>` |
| `banco_agil.tools.session_tools.<fn>` | `from banco_agil.tools.session_tools import <fn>` |
| `agno.tools.<módulo>.<Classe>` | `from agno.tools.<módulo> import <Classe>` |
| **Desconhecido** | → ver Passo 5 |

### Modelos

| provider + model_id no dict | Import Python |
|---|---|
| `provider=deepinfra`, qualquer model_id | `from banco_agil.config import get_coordinator_model` + `model=get_coordinator_model()` |
| `provider=openai` | `from agno.models.openai import OpenAIChat` |
| `provider=anthropic` | `from agno.models.anthropic import Claude` |
| Outro | `from agno.models.<provider> import <Classe>` |

Prefira sempre `get_coordinator_model()` para qualquer modelo DeepInfra — mantém
a configuração centralizada em `banco_agil/config.py`.

---

## Passo 5 — Resolver tools sem implementação

Se algum `class_path` não corresponde a nenhum arquivo em `banco_agil/tools/` nem a um
toolkit Agno existente (`agno.tools.*`), a tool foi "imaginada" no Studio e ainda não tem
implementação Python.

Para cada tool sem implementação, pergunte ao usuário:

1. O que a função deve fazer?
2. Quais parâmetros recebe (nome e tipo)?
3. O que retorna (tipo e formato do dict)?
4. Fonte dos dados (CSV em `data/`, API externa, cálculo interno)?

Com essas respostas, crie o arquivo `banco_agil/tools/<domínio>_tools.py` seguindo o padrão
existente (tipagem completa, docstring de uma linha, sem lógica de negócio nos agentes).

Não gere implementações stub (`raise NotImplementedError`) — implemente de verdade ou discuta
com o usuário antes de prosseguir.

---

## Passo 6 — Gerar o código Python de cada componente

### 6a. Agents

Para cada agente Studio-only, crie `banco_agil/agents/<slug>.py`:

```python
"""
banco_agil/agents/<slug>.py
<Nome> — <role em uma linha>.
"""

from agno.agent import Agent
from banco_agil.config import get_coordinator_model
from banco_agil.tools.<domínio>_tools import <fn1>, <fn2>


<slug>_agent = Agent(
    name="<name do dict>",
    role="<role do dict>",
    model=get_coordinator_model(),
    tools=[<fn1>, <fn2>],
    instructions=[
        # (instruções extraídas do dict, organizadas nas seções padrão)
        # ── 1. Identidade ──────────────────────────────────────────────
        # ── 2. Responsabilidades ────────────────────────────────────────
        # ── 3. Escopo ───────────────────────────────────────────────────
        # ── 4. Segurança ────────────────────────────────────────────────
    ],
    add_history_to_context=True,
    num_history_runs=<valor do dict ou 5>,
    markdown=True,
)
```

Regras:
- Copie as `instructions` exatamente como estão no dict — não reescreva nem resuma
- Organize em seções com comentários `# ──` se já não estiverem organizadas
- `model=get_coordinator_model()` sempre, independente do que está no dict (mantém consistência)
- Preserve `agent_id` do Studio no parâmetro `id=` se quiser manter continuidade de sessões

### 6b. Teams

Se houver teams Studio-only, avalie se devem:
- Substituir o Team existente em `banco_agil/team.py` (caso seja uma versão melhorada)
- Coexistir como um team adicional em um novo arquivo `banco_agil/team_<slug>.py`

Discuta com o usuário antes de sobrescrever `banco_agil/team.py`.

Para criar um team adicional, siga o padrão de `banco_agil/team.py`: função fábrica
`criar_<slug>()`, `session_state` explícito, `db=PostgresDb(db_url=DB_URL)`.

### 6c. Workflows

Crie a pasta `banco_agil/workflows/` se não existir.
Crie `banco_agil/workflows/<slug>.py` seguindo o padrão da documentação Agno:

```python
"""
banco_agil/workflows/<slug>.py
<Nome> — <descrição>.
"""

from agno.workflow import Workflow
from agno.workflow.step import Step
from banco_agil.agents import <agente1>, <agente2>


def criar_workflow_<slug>() -> Workflow:
    return Workflow(
        id="<id do dict>",
        name="<name do dict>",
        description="<description do dict>",
        steps=[
            Step(name="<step1>", agent=<agente1>),
            Step(name="<step2>", agent=<agente2>),
        ],
    )
```

Para steps com `Condition`, `Loop`, `Router` ou `Parallel`, use as classes correspondentes
de `agno.workflow` e preserve os CEL expressions do dict como strings.

---

## Passo 7 — Registrar tudo

**7a. `banco_agil/agents/__init__.py`** — adicione importações e `__all__` para cada agente novo.

**7b. `app/main.py`** — adicione agentes novos ao import e ao `Registry`; adicione workflows
ao `AgentOS` se devem ser servidos via API:

```python
from banco_agil.agents import ..., <slug>_agent
# se workflow:
from banco_agil.workflows.<slug> import criar_workflow_<slug>

registry = Registry(
    ...,
    agents=[..., <slug>_agent],
)

agent_os = AgentOS(
    ...,
    # workflows=[..., criar_workflow_<slug>()],  # se aplicável
)
```

**7c. `banco_agil/team.py`** — se um agente novo deve entrar no Team, adicione-o a `members=[...]`
e adicione a regra de roteamento nas instruções do coordenador.

---

## Passo 8 — Testar

```bash
docker compose up -d --build
docker compose logs agent-os --tail 20
```

Para cada componente adotado, envie pelo menos um prompt de golden-path:

```bash
# Agente individual
curl -s -X POST http://localhost:8000/agents/<slug>_agent/runs \
  -H "Content-Type: application/json" \
  -d '{"message": "<golden-path prompt>", "stream": false}' \
  | python -m json.tool

# Team completo
curl -s -X POST http://localhost:8000/teams/banco-agil/runs \
  -H "Content-Type: application/json" \
  -d '{"message": "<prompt que aciona o novo agente>", "session_id": "adopt-test-1", "stream": false}' \
  | python -m json.tool
```

Confirme:
- Resposta coerente com as instruções exportadas do Studio
- Nenhuma tag interna visível na resposta
- Ferramentas corretas chamadas nos logs

Se falhar, volte ao Passo 6 e ajuste.

---

## Passo 9 — Rodar evals de regressão

```bash
source .venv/bin/activate
python -m evals
```

Nenhum caso existente deve quebrar com a adição dos novos componentes.

---

## Passo 10 — Commitar, push e limpar

```bash
# Remover o script temporário
rm scripts/studio_export.py

# Commitar os componentes adotados
git add banco_agil/agents/ banco_agil/tools/ banco_agil/workflows/ \
        banco_agil/team.py app/main.py evals/cases.py \
        banco_agil/agents/__init__.py

git commit -m "feat: adota componentes do Studio — <lista dos componentes>"
git push
```

O Railway fará redeploy automático. Confirme nos logs:
```bash
railway logs --service agent-os
```

---

## Passo 11 (Projeto novo) — Criar estrutura ADLC do zero

Se o contexto for **Projeto B (novo)**, execute estes sub-passos antes do Passo 6:

1. Pergunte: nome do projeto, slug, descrição de uma linha
2. Crie a estrutura de pastas:
   ```
   <slug>/
   ├── app/main.py
   ├── <slug>/agents/__init__.py
   ├── <slug>/tools/__init__.py
   ├── <slug>/config.py
   ├── <slug>/team.py            (se houver team)
   ├── <slug>/workflows/         (se houver workflows)
   ├── evals/__init__.py
   ├── evals/__main__.py
   ├── evals/cases.py
   ├── docs/                     (copiar os 5 prompts ADLC do banco-agil)
   ├── scripts/railway/
   ├── Dockerfile
   ├── docker-compose.yml
   ├── railway.json
   ├── pyproject.toml
   └── example.env
   ```
3. Use o `banco_agil/config.py` como template para o `<slug>/config.py`
4. Use o `app/main.py` do banco-agil como template, adaptando os nomes
5. Copie os 5 prompts `docs/*.md` do banco-agil para o novo projeto
6. Depois retorne ao Passo 6 e popule com os componentes Studio exportados

---

## Relatório final

```
Componentes descobertos no Studio: <n> agents, <n> teams, <n> workflows
Componentes já em código (ignorados): <lista>
Componentes adotados: <lista com arquivos criados>
Tools novas implementadas: <lista>
Evals de regressão: PASS / FAIL
Commit: <hash>
```

Após o commit, os componentes que estavam apenas no Studio agora estão em código,
versionados no GitHub, e o Railway serve a versão mais recente automaticamente.
O Studio passa a ser usado apenas para observação (Chat, Traces, Evals) e para
novos protótipos antes do próximo ciclo ADLC.
