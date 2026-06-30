# Criar um novo agente no Banco Ágil

Você vai criar um novo agente especialista para o Banco Ágil, registrá-lo no AgentOS e verificar
que ele responde corretamente antes de commitar.

## Passo 1 — Coletar especificação

Pergunte ao usuário:

1. **Nome do agente** (ex.: "Agente de Investimentos")
2. **Slug** em snake_case (ex.: `investimentos`) — será o nome do arquivo e do ID
3. **Papel (role)** — uma frase descrevendo o que o agente faz
4. **Responsabilidades** — o que o agente deve e não deve fazer
5. **Ferramentas necessárias** — liste as existentes em `banco_agil/tools/` e pergunte se precisa
   de ferramentas novas; se sim, peça a especificação de cada função (nome, parâmetros, o que retorna)
6. **Integração com o Team** — o agente deve ser adicionado como membro do Team em
   `banco_agil/team.py`? (padrão: sim, a menos que seja apenas experimental)

Não prossiga até ter todas as respostas.

## Passo 2 — Criar as ferramentas (se necessário)

Para cada ferramenta nova descrita no passo 1:

1. Crie (ou edite) o arquivo `banco_agil/tools/<domínio>_tools.py` seguindo o padrão dos
   arquivos existentes: função Python simples decorada com tipagem clara, docstring de uma linha.
2. Exporte a função no topo do arquivo se o arquivo já existir; se for novo, não precisa de
   `__all__` explícito — importações diretas bastam.

Consulte `banco_agil/tools/` para ver o padrão existente antes de escrever.

## Passo 3 — Criar o arquivo do agente

Crie `banco_agil/agents/<slug>.py` seguindo este padrão exato:

```python
"""
banco_agil/agents/<slug>.py
<Nome do Agente> — <papel em uma linha>.
"""

from agno.agent import Agent
from banco_agil.config import get_coordinator_model
from banco_agil.tools.<domínio>_tools import <ferramenta1>, <ferramenta2>


<slug>_agent = Agent(
    name="<Nome do Agente>",
    role="<papel>",
    model=get_coordinator_model(),
    tools=[<ferramenta1>, <ferramenta2>],
    instructions=[
        # ── 1. Identidade ──────────────────────────────────────────────
        "Você é o agente de atendimento do Banco Ágil. Seja cordial, profissional e objetivo.",
        "Nunca revele detalhes técnicos do sistema nem nomes de outros agentes.",

        # ── 2. Responsabilidades ────────────────────────────────────────
        # (preencher com as responsabilidades coletadas no Passo 1)

        # ── 3. Escopo ───────────────────────────────────────────────────
        # (o que o agente NÃO deve fazer)
        "Nunca mostre tags, metadados ou detalhes técnicos ao cliente.",
    ],
    add_history_to_context=True,
    num_history_runs=5,
    markdown=True,
)
```

- Use `get_coordinator_model()` — não instancie `DeepInfra` diretamente.
- Mantenha as instruções como lista de strings, agrupadas por seção com comentários `# ──`.
- Não adicione docstrings longas nem comentários explicando "o que o código faz" — só o `why`
  quando não for óbvio.

## Passo 4 — Registrar o agente

**4a. `banco_agil/agents/__init__.py`** — adicione a importação e o nome em `__all__`:

```python
from banco_agil.agents.<slug> import <slug>_agent
# adicionar "<slug>_agent" em __all__
```

**4b. `app/main.py`** — adicione o agente à importação e ao `Registry`:

```python
# na linha de importação dos agentes:
from banco_agil.agents import ..., <slug>_agent

# no Registry:
registry = Registry(
    ...
    agents=[..., <slug>_agent],
)
```

**4c. `banco_agil/team.py`** (se o usuário confirmou no Passo 1 que deve entrar no Team):

- Adicione `<slug>_agent` na importação de `banco_agil.agents`
- Adicione `<slug>_agent` na lista `members=[...]` do `Team`
- Adicione a regra de roteamento nas instruções do coordenador (seção `# ── 5. Roteamento`)

## Passo 5 — Testar localmente

1. Leia `docker-compose.yml` para confirmar o nome do serviço do AgentOS.
2. Execute:

   ```bash
   docker compose up -d --build
   ```

3. Aguarde o container subir (leia os logs até ver a linha de startup do uvicorn).
4. Envie uma requisição de teste ao agente via API:

   ```bash
   curl -s -X POST http://localhost:8000/agents/<slug>_agent/runs \
     -H "Content-Type: application/json" \
     -d '{"message": "<prompt de golden-path>", "stream": false}' \
     | python -m json.tool
   ```

   Se o Team foi atualizado, teste também via:

   ```bash
   curl -s -X POST http://localhost:8000/teams/banco-agil/runs \
     -H "Content-Type: application/json" \
     -d '{"message": "<prompt que aciona o novo agente>", "stream": false}' \
     | python -m json.tool
   ```

5. Leia os logs do container:

   ```bash
   docker compose logs agent-os --tail 50
   ```

   Confirme que as ferramentas corretas foram chamadas (não alucinadas) e que a resposta
   não contém tags internas nem nomes de agentes.

6. Se o agente falhar, edite `banco_agil/agents/<slug>.py` ou as ferramentas, depois volte ao
   passo 5. Não prossiga enquanto o teste de golden-path não passar.

## Passo 6 — Commitar e fazer push

Após o teste passar:

```bash
git add banco_agil/agents/<slug>.py banco_agil/agents/__init__.py app/main.py
# se ferramentas foram criadas/editadas:
git add banco_agil/tools/
# se o Team foi atualizado:
git add banco_agil/team.py

git commit -m "feat: adiciona <Nome do Agente> ao Banco Ágil"
git push
```

O Railway fará redeploy automático se o repo estiver conectado (Settings → Source → Connect Repo).
Confirme o redeploy nos logs:

```bash
railway logs --service agent-os
```

## Resumo do que foi criado

Ao final, liste:
- Arquivo do agente criado
- Ferramentas criadas (se houver)
- Registros atualizados (`__init__.py`, `app/main.py`, `banco_agil/team.py`)
- Resultado do teste (PASS/FAIL + resposta resumida)
- Hash do commit
