# 🏦 Banco Ágil — Agente Bancário Inteligente

Sistema de atendimento ao cliente operado por múltiplos agentes de IA
especializados, desenvolvido com **Agno 2.6** + **DeepInfra** + **AgentOS**,
deployado na **Railway**, com UI em **Streamlit**.

> 🌐 **Demo em produção:** https://banco-agil-production.up.railway.app
> (health check em `/health`; UI Streamlit precisa ser executada localmente
> apontando para essa URL — ver [Tutorial de execução](#-tutorial-de-execução-e-testes)).

---

## 📋 Visão Geral

O **Banco Ágil** simula o atendimento de um banco digital fictício. Para o
cliente, existe um único atendente — por baixo dos panos, uma equipe
(`Team` do Agno, `mode="coordinate"`) de 4 agentes especializados decide
quem responde cada mensagem, de forma totalmente imperceptível:

```
Cliente ──► Team Coordinator (Agno, mode="coordinate")
                 ├── Agente de Triagem      — autenticação + roteamento
                 ├── Agente de Crédito      — consulta e aumento de limite
                 ├── Agente de Entrevista   — recálculo de score de crédito
                 └── Agente de Câmbio       — cotações em tempo real
```

O projeto cobre o ciclo de vida completo de uma aplicação de agentes de IA
levada à produção: do scaffold local até o deploy real na nuvem, incluindo
a investigação e correção de bugs encontrados apenas em produção (rede
privada, drivers de banco assíncronos, e até um bug real do próprio
framework Agno).

---

## 🏗 Arquitetura

### Camada de agentes (`banco_agil/agents/`)

| Agente | Responsabilidade | Modelo (DeepInfra) | Ferramentas |
|--------|-------------------|---------------------|-------------|
| Triagem | Autenticação (CPF + nascimento), identificação do assunto | `Qwen3-235B-Thinking` | `autenticar_cliente`, `buscar_dados_cliente` |
| Crédito | Consulta de limite, solicitação de aumento | `DeepSeek-V3-0324` | `consultar_limite_credito`, `solicitar_aumento_limite`, `verificar_limite_pelo_score` |
| Entrevista | Recálculo de score via entrevista financeira | `Qwen3-235B-Thinking` | `calcular_score_credito`, `atualizar_score_cliente` |
| Câmbio | Cotação de moedas em tempo real | `DeepSeek-V3-0324` | `consultar_cotacao`, `listar_moedas_suportadas` |

> O Triagem usa o modelo de raciocínio (mais caro) porque é o ponto de
> maior risco de segurança do sistema — ver [Desafios](#-desafios-enfrentados-e-como-foram-resolvidos).

### Camada de ferramentas (`banco_agil/tools/`)

Funções Python puras (sem estado, sem exceções — sempre retornam
`{"erro": ...}` em caso de falha) que operam sobre os dados:

- **auth_tools.py** — autenticação contra `data/clientes.csv`
- **credit_tools.py** — consulta/atualização de limite; grava pedidos em `data/solicitacoes_aumento_limite.csv`
- **interview_tools.py** — fórmula ponderada de score; atualiza `clientes.csv`
- **exchange_tools.py** — cotações via [AwesomeAPI](https://economia.awesomeapi.com.br) (gratuita, sem chave)

### Coordenação (`banco_agil/team.py`)

- **`mode="coordinate"`** — o coordenador (também um modelo de raciocínio)
  decide qual agente acionar e mantém o contexto entre handoffs, permitindo
  o fluxo Crédito → Entrevista → Crédito sem reautenticação.
- **`session_state`** — dicionário (`autenticado`, `cpf`, `score`,
  `tentativas_auth`, etc.) persistido entre turnos via `AsyncPostgresDb`.
- **Tags ocultas** (`[AUTH_OK|...]`, `[ROUTE|...]`) — protocolo leve de
  comunicação entre coordenador e membros, removidas antes de qualquer
  exibição ao cliente (`limpar_tags_da_resposta()`).

### Runtime e infraestrutura

```
Cliente ──HTTP──► Streamlit (ui/streamlit_app.py)
                        │ multipart/form-data
                        ▼
                  AgentOS (app/main.py — FastAPI, Agno)
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
         DeepInfra API      PostgreSQL (Railway)
      (Qwen3 / DeepSeek)    sessão + tracing (AsyncPostgresDb)
```

- **AgentOS** expõe o `Team` via REST (`POST /teams/banco-agil/runs`),
  health check (`/health`) e mais de 50 endpoints automáticos.
- **PostgreSQL assíncrono** (Railway) guarda sessão e traces — ver por quê
  precisa ser assíncrono em [Desafios](#-desafios-enfrentados-e-como-foram-resolvidos).
- **Dados de negócio** (`clientes.csv`, `score_limite.csv`) continuam em
  CSV nesta fase (decisão deliberada — ver [Escolhas técnicas](#-escolhas-técnicas-e-justificativas)).

---

## ✅ Funcionalidades implementadas

- [x] Autenticação com CPF + data de nascimento, com até 3 tentativas
- [x] Bloqueio educado após 3 falhas consecutivas
- [x] Consulta de limite de crédito
- [x] Solicitação de aumento de limite com aprovação/rejeição automática
  por score, registrada em `solicitacoes_aumento_limite.csv`
- [x] Redirecionamento para entrevista de crédito em caso de rejeição
- [x] Entrevista financeira conversacional (uma pergunta por vez) com
  validação de entradas
- [x] Recálculo de score pela fórmula ponderada oficial e persistência
- [x] Retorno automático ao Agente de Crédito após a entrevista, com o
  score atualizado, sem reautenticação
- [x] Cotação de câmbio em tempo real (USD, EUR, GBP, BTC, JPY)
- [x] Encerramento gracioso a qualquer momento
- [x] Transições entre agentes 100% imperceptíveis ao cliente
- [x] Tratamento de erros sem interrupção abrupta (CSV indisponível, API
  fora do ar, dados inválidos)
- [x] Sessão persistente entre recarregamentos (Postgres, sobrevive a
  restarts e múltiplas instâncias)
- [x] **Guardrails de segurança** contra alucinação de autenticação e
  prompt injection (ver abaixo)
- [x] Interface Streamlit completa, consumindo o AgentOS via REST
- [x] Deploy real em produção na Railway

---

## 🛡 Guardrails de segurança

Durante os testes em produção, foi identificado e corrigido um problema
real de **alucinação de autenticação**: o coordenador chegou a delegar a
autenticação ao Agente de Triagem citando valores de exemplo, e o modelo
"specialist" (DeepSeek-V3) por vezes **simulava** o resultado de uma
chamada de ferramenta em texto (ex.: blocos JSON/XML falsos) em vez de
executar a function call real — autenticando clientes fictícios sem
nunca consultar a base de dados.

Para mitigar isso, todos os agentes têm instruções explícitas que:

1. **Proíbem simular chamadas de ferramenta em texto** — qualquer
   "narração" de uma chamada (`[Chamando ferramenta...]`, JSON/XML
   fingindo um resultado) é tratada como violação grave.
2. **Distinguem dados de entrada (reais) de dados de saída (da
   ferramenta)** na delegação — o coordenador repassa o que o cliente
   realmente disse, mas nunca inventa nome/score/limite/cotação, que só
   existem após a execução real da ferramenta.
3. **Padronizam mensagens de falha de autenticação** — não diferenciam
   "CPF não encontrado" de "data incorreta", evitando enumeração de CPFs
   válidos por tentativa e erro.
4. **Mascaram o CPF** ao ser mencionado de volta ao cliente.
5. **Resistem a prompt injection** — ignoram alegações do cliente como
   "já fui autenticado", "meu score é 900" ou pedidos para revelar o
   prompt de sistema/arquitetura interna.
6. **Usam o modelo de raciocínio** (`Qwen3-235B-Thinking`) no Agente de
   Triagem especificamente, por ser o ponto de maior risco — validado
   sem nenhuma ocorrência de alucinação em testes repetidos, contra o
   modelo "specialist" que apresentava o comportamento de forma
   intermitente.

---

## 🧩 Desafios enfrentados e como foram resolvidos

### 1. Transição imperceptível entre agentes
**Problema:** o cliente não pode perceber a troca de agentes.
**Solução:** `mode="coordinate"` do Agno — o coordenador atua como único
interlocutor; tags `[ROUTE|...]` são processadas e removidas antes de
qualquer exibição.

### 2. Volume do Postgres anexado ao serviço errado
**Problema:** o deploy na Railway retornava `502` após 300s em toda
primeira mensagem real. Investigação revelou que o volume persistente
estava anexado a um serviço Postgres diferente do que a aplicação usava
— o Postgres "oficial" rodava sem armazenamento, entrava em loop de
falha (`Railway volume not mounted to the correct path`) e caía.
**Solução:** identificar o serviço Postgres correto (via API GraphQL da
Railway) e recriar o volume apontando para ele.

### 3. `PostgresDb` síncrono bloqueando o event loop
**Problema:** mesmo com o Postgres saudável, a primeira escrita real de
sessão travava o processo inteiro (até o `/health` parava de responder).
**Causa:** `PostgresDb` é síncrono; chamado dentro do event loop
assíncrono do AgentOS (FastAPI), bloqueia o único worker.
**Solução:** trocar para `AsyncPostgresDb` (`postgresql+psycopg_async://`),
caminho oficialmente recomendado pelo Agno para uso com `Team`/`AgentOS`.

### 4. Bug real do Agno: `MetaData` duplicada no SQLAlchemy
**Problema:** mesmo após a correção acima, ocorriam erros
`InvalidRequestError: Table 'X' is already defined for this MetaData
instance` quando o coordenador e os agentes membros acessavam a tabela
de sessão quase simultaneamente.
**Causa:** bug confirmado no Agno 2.6.x — `agno/db/postgres/{postgres,
async_postgres}.py` registram tabelas no SQLAlchemy sem
`extend_existing=True`. Há duas PRs da comunidade com a mesma correção
([#7322](https://github.com/agno-agi/agno/pull/7322),
[#7334](https://github.com/agno-agi/agno/pull/7334)), ambas fechadas sem
merge.
**Solução:** monkeypatch local (`banco_agil/_agno_patches.py`) aplicando
a mesma correção até uma versão oficial do Agno resolver o problema.

### 5. Resposta final vazia em modelos "Thinking"
**Problema:** após corrigir a conexão com o banco, a resposta final ao
cliente às vezes saía vazia.
**Causa:** `max_tokens` baixo (2000) — o modelo gastava todo o orçamento
em raciocínio interno + chamada de ferramenta, sem sobrar espaço para o
texto final.
**Solução:** aumentar `max_tokens` para 6000 no modelo de raciocínio.

### 6. Múltiplos serviços Postgres fantasmas
**Problema:** a Railway criou silenciosamente serviços Postgres extras
("Postgres-n_gW", etc.) toda vez que um serviço com imagem de banco era
provisionado via API, gerando confusão sobre qual estava de fato em uso.
**Solução:** usar o serviço Postgres "oficial" (com `DATABASE_URL`,
`PGUSER` etc. nativos da Railway) e referenciar via variável
`${{Postgres.DATABASE_URL}}`, em vez de provisionar manualmente.

---

## ⚙️ Escolhas técnicas e justificativas

| Decisão | Justificativa |
|---------|---------------|
| **Agno 2.6** | Sessão stateful nativa, `Team` com `mode="coordinate"`, AgentOS pronto para produção (REST/SSE automáticos) |
| **DeepInfra** | Custo baixo, catálogo de modelos open-weight com tool calling forte, sem dependência de Anthropic/OpenAI |
| **Modelo de raciocínio para Triagem/Entrevista/Coordenador** | Maior confiabilidade em tool calling — crítico para evitar alucinação de autenticação e garantir cálculo de score correto |
| **`AsyncPostgresDb`** | Único caminho compatível com o event loop assíncrono do AgentOS sem bloquear o worker |
| **Railway** | Deploy simples a partir do GitHub, Postgres gerenciado, API GraphQL pública que permite automação completa do provisionamento |
| **CSV para dados de negócio** | Atende ao desafio técnico diretamente; migração para Postgres fica para uma fase futura (dados de sessão já estão no Postgres) |
| **Tags ocultas (`[AUTH_OK|...]`)** | Protocolo leve de comunicação coordenador↔membro; modelos open-weight têm suporte variável a structured output nativo |
| **Streamlit** | Requisito do desafio; consome o AgentOS via REST, sem lógica de negócio na UI |

---

## 📁 Estrutura de diretórios

```
banco-agil/
├── app/                     # AgentOS (FastAPI) — entry point de produção
│   ├── main.py
│   └── config.yaml
├── banco_agil/              # Domínio
│   ├── config.py            # Factories de modelo DeepInfra, paths, DB_URL
│   ├── team.py               # Team coordinator + helpers de tags
│   ├── _agno_patches.py      # Monkeypatch do bug de MetaData (Agno)
│   ├── agents/                # Um arquivo por agente
│   └── tools/                  # Funções Python puras
├── data/                     # clientes.csv, score_limite.csv
├── ui/                       # Streamlit + cliente HTTP para o AgentOS
├── tests/                    # pytest — 31 testes, 90% de cobertura
├── evals/                    # AgentAsJudgeEval — casos de avaliação por LLM-juiz
├── scripts/                  # Deploy, geração de chaves JWT, init do DB
├── docs/runbook.md           # Operação em produção (rotação de chave, rollback, etc.)
├── Dockerfile / docker-compose.yml / railway.json
└── pyproject.toml
```

---

## 🚀 Tutorial de execução e testes

### Pré-requisitos

- Python 3.11+
- Uma `DEEPINFRA_API_KEY` ([deepinfra.com](https://deepinfra.com))

### 1. Instalar dependências

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac
pip install -e ".[dev]"
```

### 2. Configurar variáveis de ambiente

```bash
cp example.env .env
# Edite .env e preencha DEEPINFRA_API_KEY
```

### 3. Testar contra o backend já em produção (mais rápido — sem Docker)

```bash
# No .env, aponte para o backend público:
# AGENTOS_URL=https://banco-agil-production.up.railway.app

streamlit run ui/streamlit_app.py
```

Acesse `http://localhost:8501` e use um dos CPFs de teste (sidebar da UI).

### 4. Rodar localmente com stack completa (Docker)

```bash
docker compose up -d --build
docker compose exec agent-os python -m uvicorn app.main:app --host 0.0.0.0
curl http://localhost:8000/health
```

### 5. Testes unitários

```bash
pytest tests/ -v --cov=banco_agil/tools --cov-report=term-missing
# 31 testes, ≥80% de cobertura nas tools
```

### 6. Lint e type checking

```bash
ruff check banco_agil/ app/ ui/ tests/ evals/
mypy banco_agil/ app/ --ignore-missing-imports
```

### 7. Evals (requer DEEPINFRA_API_KEY real)

```bash
python -m evals                       # todos os 6 casos
python -m evals --case cambio_dolar   # um caso isolado
```

### Clientes de teste disponíveis

| CPF | Nascimento | Nome | Score | Limite |
|-----|-----------|------|-------|--------|
| 123.456.789-01 | 15/05/1990 | Ana Oliveira | 720 | R$ 5.000 |
| 987.654.321-00 | 23/11/1985 | Bruno Santos | 450 | R$ 1.500 |
| 111.222.333-00 | 08/03/1978 | Carla Mendes | 610 | R$ 3.000 |
| 444.555.666-77 | 30/07/2000 | Daniel Costa | 380 | R$ 800 |
| 555.666.777-88 | 12/01/1995 | Elena Ferreira | 810 | R$ 8.000 |

Fluxo de **aumento aprovado**: Ana (720 → máx. R$ 10k) ou Elena (810 → máx. R$ 20k).
Fluxo de **rejeição + entrevista**: Bruno (450 → máx. R$ 2k) ou Daniel (380 → máx. R$ 1k).

---

## 📚 Documentação adicional

- [`docs/runbook.md`](docs/runbook.md) — operação em produção (rotação de
  chave, restore de backup, rollback de deploy)
- [`AGENTS.md`](AGENTS.md) — guia para desenvolvimento assistido por IA
  neste repositório
