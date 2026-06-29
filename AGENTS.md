# AGENTS.md — Guia do Claude Code: Banco Ágil

> **Este arquivo é o ponto de partida para o Claude Code.**
> Leia-o integralmente antes de tocar em qualquer arquivo.

---

## O que é este projeto

**Banco Ágil** é um sistema de atendimento bancário por múltiplos agentes de IA.
Stack: **Agno 2.6** (framework + AgentOS) · **DeepInfra** (LLM) · **Railway** (cloud) · **PostgreSQL/pgvector** (storage) · **Streamlit** (UI).

O cliente conversa com um único atendente que, por baixo, é um `Team` Agno com 4 agentes especializados: Triagem, Crédito, Entrevista de Crédito e Câmbio.

**Spec completa:** `docs/SDD.md` — leia a seção de tasks antes de qualquer implementação.

---

## Mapa de arquivos (o que cada um faz)

```
banco-agil/
│
│  ← ENTRY POINTS (não altere sem checar dependentes)
├── app/main.py                 AgentOS FastAPI app — registra Team + serve REST/SSE
├── ui/streamlit_app.py         UI cliente — consome AgentOS via HTTP
├── ui/api_client.py            HTTP client para AgentOS (BancoAgilClient)
│
│  ← DOMÍNIO (lógica de negócio)
├── banco_agil/config.py        Constantes, env vars, factory de modelos DeepInfra
├── banco_agil/team.py          Cria o Team coordinator (mode="coordinate")
│
│  ← AGENTES (um arquivo por agente)
├── banco_agil/agents/triagem.py       Autentica via CPF + data, emite [AUTH_OK]/[AUTH_FAIL]
├── banco_agil/agents/credito.py       Consulta limite, processa aumento, emite [ROUTE|entrevista]
├── banco_agil/agents/entrevista.py    Coleta 5 campos, calcula score, emite [ROUTE|credito|score_atualizado=X]
├── banco_agil/agents/cambio.py        Busca cotação via AwesomeAPI
│
│  ← FERRAMENTAS (funções Python puras, sem estado)
├── banco_agil/tools/auth_tools.py     autenticar_cliente(), buscar_dados_cliente()
├── banco_agil/tools/credit_tools.py   consultar_limite_credito(), solicitar_aumento_limite(), verificar_limite_pelo_score()
├── banco_agil/tools/interview_tools.py calcular_score_credito(), atualizar_score_cliente()
├── banco_agil/tools/exchange_tools.py  consultar_cotacao(), listar_moedas_suportadas()
│
│  ← DADOS (base de clientes e scores — CSV no MVP, Postgres na Fase 2)
├── data/clientes.csv                  CPF | data_nascimento | nome | score | limite_credito
├── data/score_limite.csv              score_minimo | score_maximo | limite_maximo
├── data/solicitacoes_aumento_limite.csv  (gerado em runtime)
│
│  ← TESTES
├── tests/test_auth_tools.py
├── tests/test_credit_tools.py
├── tests/test_interview_tools.py
├── tests/test_exchange_tools.py
│
│  ← EVALS (AgentAsJudgeEval — testa o comportamento do LLM)
├── evals/cases.py              Declaração dos casos de eval
├── evals/__main__.py           Runner: python -m evals
│
│  ← INFRA
├── Dockerfile                  Container da aplicação AgentOS
├── docker-compose.yml          Stack local: agent-os + postgres + pgvector
├── railway.json                Configuração de deploy Railway
├── pyproject.toml              Dependências Python (substitui requirements.txt)
├── example.env                 Variáveis de ambiente necessárias (copiar para .env)
│
│  ← SCRIPTS
├── scripts/seed_db.py          Migra CSV → Postgres
├── scripts/railway_up.sh       Deploy Railway em 1 comando
└── docs/SDD.md                 Spec completa (requisitos, ADRs, tasks)
```

---

## Regras invioláveis (invariantes do projeto)

**Nunca quebre estas regras. Se uma task exigir isso, pare e peça confirmação.**

1. **LLM provider é exclusivamente DeepInfra.**
   - Import correto: `from agno.models.deepinfra import DeepInfra`
   - Proibido: `anthropic`, `openai`, `Claude`, `OpenAIChat` em arquivos de agente.
   - Verificar: `grep -r "from agno.models.anthropic\|from agno.models.openai" banco_agil/` deve retornar vazio.

2. **Tags ocultas nunca chegam ao cliente.**
   - Todo output do Team passa por `limpar_tags_da_resposta()` antes de ser exibido.
   - Tags: `[AUTH_OK|...]`, `[AUTH_FAIL]`, `[ROUTE|...]`.

3. **Credenciais apenas em variáveis de ambiente.**
   - Proibido hardcodar qualquer key ou senha.
   - Verificar: `git grep -rn "di_\|sk-ant\|password\s*=\s*['\"]"` deve retornar vazio.

4. **Tools são funções Python puras.**
   - Sem estado global, sem import de agentes.
   - Entradas tipadas, saídas sempre `dict` (Agno gera JSON Schema automaticamente).
   - Erros retornam `{"erro": "mensagem"}` — nunca levantam exceção para o agente.

5. **Cada agente tem escopo restrito.**
   - Triagem: apenas autenticação e identificação.
   - Crédito: apenas consulta e aumento de limite.
   - Entrevista: apenas coleta de dados e recálculo de score.
   - Câmbio: apenas cotação de moedas.
   - Nenhum agente executa ações de outro.

6. **Fórmula de score é imutável (definida no desafio).**
   ```python
   score = (renda / (despesas + 1)) * 30
           + peso_emprego[tipo_emprego]
           + peso_dependentes[num_dependentes]
           + peso_dividas[tem_dividas]
   # Resultado clampado em [0, 1000]
   ```

7. **`app/main.py` é a única fonte de verdade para registro de agentes.**
   - Todo novo agente criado DEVE ser adicionado ao `AgentOS(teams=[...])`.
   - Após criar agente, reiniciar o container e smoke-test via `curl`.

---

## Modelos DeepInfra (tabela de seleção)

| Situação | Modelo | Config |
|----------|--------|--------|
| Team coordinator e os 4 agentes (Triagem, Crédito, Entrevista, Câmbio) | `Qwen/Qwen3-235B-A22B-Thinking-2507` | `temperature=0.3` |
| Fallback (se model acima falhar) | `meta-llama/Meta-Llama-3.3-70B-Instruct` | `temperature=0.5` |

> **Por que todos no modelo de raciocínio?** O `deepseek-ai/DeepSeek-V3-0324`
> ("specialist", mais barato) demonstrou em produção, repetidas vezes,
> deixar de chamar a ferramenta real e inventar uma resposta de texto —
> primeiro no Triagem (autenticação), depois no Câmbio (cotação,
> inclusive copiando para o cliente um trecho de exemplo do próprio
> prompt interno). `get_specialist_model()` continua existindo em
> `config.py` para uso futuro caso a relação custo/confiabilidade mude
> (ex.: um modelo specialist com tool-calling mais confiável no catálogo
> da DeepInfra), mas nenhum agente o usa atualmente.

**Factory functions em `banco_agil/config.py`:**
```python
from banco_agil.config import get_coordinator_model

model=get_coordinator_model()
```

---

## Template padrão de agente

Ao criar ou editar um agente, use **exatamente** este padrão:

```python
"""
banco_agil/agents/<nome>.py
Agente de <Nome> — <descrição em uma linha>.
"""

from agno.agent import Agent
from banco_agil.config import get_coordinator_model
from banco_agil.tools.<modulo> import funcao_a, funcao_b


<nome>_agent = Agent(
    name="Agente de <Nome>",         # Nome humano, sem abreviações
    role="<Descrição do papel>",     # Uma frase clara
    model=get_coordinator_model(),   # Ver nota na tabela de seleção acima

    tools=[funcao_a, funcao_b],      # Apenas tools do escopo deste agente

    instructions=[
        # ── 1. Identidade ──────────────────────────────────────────────
        "Você é o <papel> do Banco Ágil. Tom: cordial, profissional, direto.",
        "NUNCA revele ao cliente que você é um agente separado ou que existe uma equipe.",

        # ── 2. Fluxo principal ─────────────────────────────────────────
        "Ao receber a primeira mensagem: <passo 1>.",
        "Em seguida: <passo 2>.",
        # ... (uma instrução por passo, do mais importante ao menos)

        # ── 3. Tratamento de erros ─────────────────────────────────────
        "Se a ferramenta retornar {'erro': ...}: informe o cliente sem detalhes técnicos.",
        "Sempre ofereça uma alternativa quando não puder atender.",

        # ── 4. Tags de saída (somente se necessário) ───────────────────
        "Ao autenticar com sucesso: inclua [AUTH_OK|cpf=X|nome=Y|score=Z|limite=W].",
        # ou: "Para redirecionar ao crédito: inclua [ROUTE|credito]."

        # ── 5. Restrições de escopo ────────────────────────────────────
        "Não execute ações de outros agentes (câmbio, entrevista, etc.).",
        "Nunca mencione tags, metadados ou nomes de ferramentas ao cliente.",
    ],

    add_history_to_context=True,
    num_history_runs=5,          # 3 para Câmbio, 8 para Entrevista
    markdown=True,
)
```

---

## Guia de tarefas comuns

### Criar um novo agente

1. Crie `banco_agil/agents/<nome>.py` usando o template acima.
2. Exporte em `banco_agil/agents/__init__.py`:
   ```python
   from banco_agil.agents.<nome> import <nome>_agent
   __all__ = [..., "<nome>_agent"]
   ```
3. Adicione ao `Team` em `banco_agil/team.py`:
   ```python
   members=[triagem_agent, credito_agent, ..., <nome>_agent]
   ```
4. Registre no `AgentOS` em `app/main.py` (se for agente standalone além do Team):
   ```python
   agent_os = AgentOS(teams=[team], agents=[<nome>_agent])
   ```
5. Adicione caso de eval em `evals/cases.py`.
6. Reinicie e smoke-test:
   ```bash
   docker compose restart agent-os
   curl -s -X POST http://localhost:8000/teams/banco-agil/runs \
     -H "Content-Type: application/json" \
     -d '{"message": "oi", "session_id": "test-001"}' | python -m json.tool
   ```

### Adicionar uma nova tool

1. Crie a função em `banco_agil/tools/<modulo>.py`:
   ```python
   def minha_tool(param_a: str, param_b: float) -> dict:
       """Descrição clara — o Agno usa como doc do function calling."""
       try:
           # lógica...
           return {"resultado": valor}
       except Exception as exc:
           return {"erro": f"Falha em minha_tool: {exc}"}
   ```
2. Exporte em `banco_agil/tools/__init__.py`.
3. Adicione ao agente: `tools=[..., minha_tool]`.
4. Escreva teste em `tests/test_<modulo>.py`.
5. Verifique: `pytest tests/test_<modulo>.py -v`.

### Trocar o modelo de um agente

```python
# Em banco_agil/agents/<nome>.py
# Antes:
model=get_specialist_model()
# Depois (ex: promover para coordinator model):
model=get_coordinator_model()
```
Sempre justificar no commit message por que o modelo foi promovido.

### Alterar instructions de um agente

- Edite `banco_agil/agents/<nome>.py` → seção `instructions`.
- Estrutura das 5 seções é obrigatória (identidade, fluxo, erros, tags, restrições).
- Após editar, rode o eval do agente:
  ```bash
  python -m evals --case <nome_do_caso>
  ```

### Migrar CSV para Postgres (Fase 2)

Quando o SDD indicar TASK-012:
1. Edite `banco_agil/tools/auth_tools.py`:
   - Substitua `pd.read_csv(CLIENTES_CSV)` por query Postgres.
   - Use `psycopg` diretamente ou via `sqlalchemy`.
2. Mesmo padrão para `credit_tools.py` e `interview_tools.py`.
3. Rode `python scripts/seed_db.py` para popular o banco.
4. Confirme: `pytest tests/ -v`.

### Adicionar um eval

Em `evals/cases.py`, adicione ao array `CASES`:
```python
AgentAsJudgeEval(
    name="<nome_snake_case>",            # ex: "cambio_euro"
    team=team,
    prompts=[
        "mensagem inicial",
        "resposta do usuário",           # simular fluxo multi-turno
        "próxima mensagem",
    ],
    rubric=(
        "O agente deve <comportamento esperado>. "
        "A resposta NÃO deve conter colchetes, nomes de agentes ou metadados."
    ),
    pass_threshold=0.8,                  # 80% = passar
),
```

---

## Comandos de validação (rode após cada mudança)

```bash
# Verificar se imports DeepInfra estão corretos (deve retornar vazio)
grep -rn "from agno.models.anthropic\|from agno.models.openai" banco_agil/

# Verificar sem credenciais hardcoded (deve retornar vazio)
git grep -rn "di_\|sk-ant\|sk-proj" -- "*.py"

# Unit tests das tools (deve passar ≥ 80% cobertura)
pytest tests/ -v --cov=banco_agil/tools --cov-report=term-missing

# Type checking
mypy banco_agil/ --ignore-missing-imports

# Lint
ruff check banco_agil/ app/ tests/

# Smoke test AgentOS local
curl -s http://localhost:8000/health | python -m json.tool

# Teste de chat básico (requer AgentOS rodando)
curl -s -X POST http://localhost:8000/teams/banco-agil/runs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${AGENTOS_API_KEY}" \
  -d '{"message": "Olá", "session_id": "smoke-test-001"}' \
  | python -m json.tool

# Evals completos (requer DEEPINFRA_API_KEY válida)
python -m evals

# Eval isolado
python -m evals --case auth_happy_path

# Verificar que tags não vazam (rodar contra sessão real de teste)
python scripts/check_tag_leakage.py   # criar este script se não existir
```

---

## Anti-padrões — o que NÃO fazer

| ❌ Errado | ✅ Correto |
|----------|-----------|
| `raise Exception("falha")` em uma tool | `return {"erro": "falha"}` |
| `from agno.models.anthropic import Claude` | `from agno.models.deepinfra import DeepInfra` |
| Checar `session_state` dentro de uma tool | Receber `cpf` como parâmetro da tool |
| Agente de Crédito chamando `consultar_cotacao()` | Agente de Câmbio é o único que chama essa tool |
| Strings hardcodadas de API key | `os.getenv("DEEPINFRA_API_KEY")` via `config.py` |
| `print()` para debug em produção | `logging.getLogger(__name__).debug(...)` |
| Múltiplas tools com nomes ambíguos | Nomes descritivos: `solicitar_aumento_limite` (não `atualizar`) |
| Editar `data/clientes.csv` manualmente | Usar `scripts/seed_db.py` ou a tool `atualizar_score_cliente()` |
| Um único arquivo `agents.py` gigante | Um arquivo por agente em `banco_agil/agents/` |
| Session state global em `team.py` | `session_state` é por sessão (`criar_equipe(session_id)`) |

---

## Variáveis de ambiente obrigatórias

| Variável | Obrigatória | Onde usar |
|----------|-------------|-----------|
| `DEEPINFRA_API_KEY` | ✅ Sim | `banco_agil/config.py` → DeepInfra client |
| `DB_URL` | ✅ Sim (Postgres) | `banco_agil/config.py` → PostgresDb |
| `AGENTOS_URL` | Para UI Streamlit | `ui/api_client.py` |
| `AGENTOS_API_KEY` | Para UI Streamlit | `ui/api_client.py` |
| `JWT_VERIFICATION_KEY` | Para os.agno.com live | `app/main.py` / Railway env |
| `COORDINATOR_MODEL_ID` | Opcional | Default: `Qwen/Qwen3-235B-A22B-Thinking-2507` |
| `SPECIALIST_MODEL_ID` | Opcional | Default: `deepseek-ai/DeepSeek-V3-0324` |
| `APP_ENV` | Opcional | `dev` \| `staging` \| `production` |
| `LOG_LEVEL` | Opcional | `INFO` em prod, `DEBUG` em dev |
| `AGNO_TELEMETRY` | Opcional | `false` para desabilitar telemetria Agno |

**Nunca commitar `.env` — está no `.gitignore`.**

---

## Clientes de teste disponíveis

| CPF | Nascimento | Nome | Score | Limite |
|-----|-----------|------|-------|--------|
| 12345678901 | 1990-05-15 | Ana Oliveira | 720 | R$ 5.000 |
| 98765432100 | 1985-11-23 | Bruno Santos | 450 | R$ 1.500 |
| 11122233300 | 1978-03-08 | Carla Mendes | 610 | R$ 3.000 |
| 44455566677 | 2000-07-30 | Daniel Costa | 380 | R$ 800 |
| 55566677788 | 1995-01-12 | Elena Ferreira | 810 | R$ 8.000 |

Clientes para testar fluxo de **aumento aprovado:** Ana (720 → limite máx R$ 10k), Elena (810 → limite máx R$ 20k).
Clientes para testar **rejeição + entrevista:** Bruno (450 → máx R$ 2k), Daniel (380 → máx R$ 1k).

---

## Tags ocultas — referência rápida

| Tag | Emitida por | Efeito no coordinator |
|-----|------------|----------------------|
| `[AUTH_OK\|cpf=X\|nome=Y\|score=Z\|limite=W]` | Triagem | Seta `autenticado=True`, cpf, nome, score, limite no session_state |
| `[AUTH_FAIL]` | Triagem | Incrementa `tentativas_auth`; se ≥3, seta `encerrado=True` |
| `[ROUTE\|credito]` | Triagem ou Entrevista | Roteia próxima mensagem para Crédito |
| `[ROUTE\|entrevista]` | Crédito | Roteia próxima mensagem para Entrevista |
| `[ROUTE\|credito\|score_atualizado=X]` | Entrevista | Roteia para Crédito e atualiza score no state |
| `[ROUTE\|cambio]` | Triagem | Roteia próxima mensagem para Câmbio |

**Limpar tags antes de exibir:**
```python
from banco_agil.team import limpar_tags_da_resposta
texto_limpo = limpar_tags_da_resposta(texto_bruto)
```

---

## Setup rápido (dev local)

```bash
# 1. Clone e configure
git clone https://github.com/<org>/banco-agil.git && cd banco-agil
cp example.env .env         # editar: DEEPINFRA_API_KEY obrigatória

# 2. Suba o stack
docker compose up -d --build

# 3. Seed do banco
docker compose exec agent-os python scripts/seed_db.py

# 4. Verifique
curl http://localhost:8000/health
# → {"status": "healthy"}

# 5. UI cliente (opcional)
pip install streamlit && streamlit run ui/streamlit_app.py
```

---

## Registro de agentes no AgentOS (app/main.py)

```python
# TODA alteração em agentes deve atualizar este registro.
# Manter esta tabela em sincronia com o arquivo:

# Agente             | Arquivo                          | Registrado como
# -------------------+----------------------------------+----------------
# Triagem            | banco_agil/agents/triagem.py     | membro do Team
# Crédito            | banco_agil/agents/credito.py     | membro do Team
# Entrevista         | banco_agil/agents/entrevista.py  | membro do Team
# Câmbio             | banco_agil/agents/cambio.py      | membro do Team
# BancoAgil Team     | banco_agil/team.py               | teams=[team]
```

---

## Checklist pré-commit

Copie esta lista para cada PR/commit de mudança em agentes ou tools:

```
[ ] grep -r "anthropic\|openai" banco_agil/ retorna vazio
[ ] pytest tests/ -v passa sem erros
[ ] ruff check banco_agil/ app/ sem erros
[ ] mypy banco_agil/ sem erros críticos
[ ] curl http://localhost:8000/health → 200
[ ] Smoke test de chat basic passa (ver comando acima)
[ ] python -m evals roda sem crash (≥90% pass)
[ ] AGENTS.md está atualizado se estrutura mudou
[ ] Nenhuma credencial hardcoded
[ ] README.md reflete mudanças (se visível ao usuário)
```

---

*AGENTS.md gerado em 27 jun 2026 — atualizar sempre que a estrutura do projeto mudar.*
