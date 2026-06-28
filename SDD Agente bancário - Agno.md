# SDD — Agente Bancário Inteligente "Banco Ágil"
## Spec Driven Development · v1.0 · 27 jun 2026

> Documento de especificação para desenvolvimento orientado pelo Claude Code.
> Stack: **Agno** (framework + AgentOS) · **DeepInfra** (LLM gateway) · **Railway** (cloud runtime) · **PostgreSQL/pgvector** (storage) · **Streamlit** (UI cliente) · **os.agno.com** (control plane).

---

## Índice

1. [Contexto e objetivo](#1-contexto-e-objetivo)
2. [Esclarecimento técnico: o que significa "Agno Cloud"](#2-esclarecimento-tcnico-o-que-significa-agno-cloud)
3. [Requisitos funcionais (REQ-F)](#3-requisitos-funcionais-req-f)
4. [Requisitos não-funcionais (REQ-NF)](#4-requisitos-no-funcionais-req-nf)
5. [Arquitetura](#5-arquitetura)
6. [Decisões técnicas (ADRs)](#6-decises-tcnicas-adrs)
7. [Stack tecnológica](#7-stack-tecnolgica)
8. [Modelo de dados](#8-modelo-de-dados)
9. [Especificação dos agentes](#9-especificao-dos-agentes)
10. [Especificação das ferramentas (tools)](#10-especificao-das-ferramentas-tools)
11. [Contratos de API (AgentOS)](#11-contratos-de-api-agentos)
12. [Configuração de modelos (DeepInfra)](#12-configurao-de-modelos-deepinfra)
13. [Estrutura de diretórios alvo](#13-estrutura-de-diretrios-alvo)
14. [Delta vs. scaffold atual](#14-delta-vs-scaffold-atual)
15. [Plano de implementação (tasks para Claude Code)](#15-plano-de-implementao-tasks-para-claude-code)
16. [Testes e evals](#16-testes-e-evals)
17. [Deploy e operação](#17-deploy-e-operao)
18. [Observabilidade e governança CoE IA](#18-observabilidade-e-governana-coe-ia)
19. [Roadmap pós-MVP](#19-roadmap-ps-mvp)
20. [Apêndices](#20-apndices)

---

## 1. Contexto e objetivo

### 1.1 Contexto

O **Banco Ágil** é um sistema de atendimento ao cliente operado por agentes de IA especializados, definido no documento *Desafio Técnico: Agentes de IA*. O scaffold inicial foi construído em iteração anterior (ver `README.md`) usando Agno com `Claude(id="claude-sonnet-4-6")` rodando localmente com SQLite e UI Streamlit.

Este SDD especifica a **evolução do scaffold para uma arquitetura cloud-ready** que mantém toda a lógica de negócio, substitui o provedor LLM por DeepInfra (open-weight, custo otimizado) e migra o runtime para AgentOS deployado no Railway com controle via `os.agno.com`.

### 1.2 Objetivo

Entregar um sistema multi-agente de atendimento bancário que:

- Cumpre integralmente o Desafio Técnico (4 agentes, fluxo de autenticação, crédito, entrevista e câmbio).
- Roda em ambiente cloud sem servidor próprio (Railway BYOC, sem self-hosted local).
- Usa **DeepInfra** como provedor único de LLMs (sem dependência da Claude API ou OpenAI API).
- É operado pelo time CoE IA via **control plane os.agno.com** (chat, traces, evals, RBAC).
- Mantém a UI Streamlit como interface cliente, agora consumindo a API REST do AgentOS.
- É desenvolvido por **Claude Code** orientado por este SDD, usando o **Agno Skill** oficial.

### 1.3 Não-objetivos (fora de escopo)

- Self-hosted em servidor próprio Cogna (postergado para fase 2).
- Integração com sistemas bancários reais (Core Banking, PIX, etc.).
- Multi-tenancy multi-banco.
- Análise de risco anti-fraude (apenas validação de autenticação simples).

### 1.4 Critério de sucesso (Definition of Done)

| # | Critério | Verificação |
|---|----------|-------------|
| 1 | Os 4 agentes do desafio funcionam end-to-end | Evals automáticos passam ≥ 90% |
| 2 | Sistema deployado no Railway com domínio público | `curl https://<domain>/health` retorna 200 |
| 3 | Control plane conectado ao AgentOS | Login em `os.agno.com` mostra os agentes ativos |
| 4 | DeepInfra é o único provedor LLM | `grep -r "anthropic\|openai" --include="*.py"` retorna apenas imports do `agno.models.deepinfra` |
| 5 | UI Streamlit consome API REST do AgentOS | `streamlit run app.py` chama `https://<railway-domain>/agents/<id>/runs` |
| 6 | Custos < R$ 50/mil execuções | Dashboard DeepInfra confirma |
| 7 | Documentação completa | `README.md`, este SDD, `AGENTS.md` |

---

## 2. Esclarecimento técnico: o que significa "Agno Cloud"

> **Importante.** Agno **não oferece** um runtime totalmente gerenciado (SaaS) onde o código roda nos servidores da Agno. O modelo de produto é **BYOC — Bring Your Own Cloud**: o runtime (AgentOS) é um container Docker que você hospeda. Agno permite que você mantenha controle sobre seu stack — dados, contexto, ferramentas, permissões, memória e human-review loops — rodando em sua própria cloud, gerenciado por uma UI bonita.

### 2.1 Arquitetura Agno em três camadas

| Camada | Localização | Responsabilidade |
|--------|------------|-----------------|
| **Framework (SDK Python)** | Seu código | Define Agents, Teams, Workflows, Tools |
| **Runtime (AgentOS)** | **Sua cloud** (Railway, AWS, GCP) | FastAPI app que serve os agentes via REST/SSE |
| **Control Plane** | `os.agno.com` (hospedado por Agno) | UI Web que conecta ao seu runtime |

### 2.2 Modelo escolhido: Railway + os.agno.com

Como o objetivo é "não usar self-hosted local", a melhor opção é deployar o AgentOS no **Railway** (PaaS com deploy via `railway up`) e gerenciá-lo pelo `os.agno.com`. Esse caminho:

- Não exige servidor próprio Cogna.
- Tem template oficial da Agno (`agno-agi/agentos-railway-template`).
- Custo Railway: ~US$ 5–20/mês para tráfego de demo.
- Deploy contínuo via `git push` em branch `main`.
- Dados persistem em Postgres provisionado no próprio Railway.
- Control plane `os.agno.com` conecta via domínio público do Railway.

> **Nota.** O acesso "live" do `os.agno.com` (conectar a domínio público em produção) requer uma assinatura Pro do plano Agno, com o coupon code PLATFORM30 disponibilizado para 1 mês de teste gratuito. Alternativamente, é possível gerar seu próprio par de chaves RSA/EC e usar JWT_VERIFICATION_KEY local — o platform não exige que a chave venha do os.agno.com, desde que tokens recebidos validem corretamente. Em ambiente local/dev o uso é gratuito.

### 2.3 O que muda em relação ao scaffold atual

| Camada | Scaffold atual | Alvo SDD |
|--------|---------------|---------|
| LLM provider | `Claude(id="claude-sonnet-4-6")` | `DeepInfra(id="<modelo>")` |
| Storage | SQLite local (`tmp/banco_agil.db`) | PostgreSQL + pgvector no Railway |
| Runtime | Python rodando localmente | AgentOS FastAPI app, container Docker no Railway |
| UI cliente | Streamlit chamando `team.run()` localmente | Streamlit chamando AgentOS REST API remoto |
| UI dev/ops | (não tinha) | `os.agno.com` conectado ao AgentOS Railway |
| Tracing | (não tinha) | Nativo do AgentOS, persistido em Postgres |

---

## 3. Requisitos funcionais (REQ-F)

> Formato: cada requisito tem ID, descrição, critérios de aceite (Given/When/Then) e mapeamento para tasks de implementação.

### REQ-F-001 — Agente de Triagem deve autenticar via CPF + data de nascimento

**Descrição.** Recebe CPF e data de nascimento, valida contra `clientes.csv` (ou tabela migrada) e direciona para o agente apropriado.

**Critérios de aceite.**

- **Given** o cliente informa CPF `123.456.789-01` e nascimento `15/05/1990` que existem na base
- **When** o Agente de Triagem chama `autenticar_cliente()`
- **Then** retorna `sucesso=True` e o estado `session_state['autenticado']` muda para `True`

- **Given** o cliente erra os dados 3 vezes consecutivas
- **When** ocorre a terceira falha
- **Then** o atendimento é encerrado com mensagem cordial e `session_state['encerrado'] = True`

**Tasks relacionadas.** TASK-005, TASK-010, TASK-015.

### REQ-F-002 — Agente de Crédito deve consultar e processar aumentos de limite

**Descrição.** Após autenticação, permite consulta de limite atual e solicitação de aumento. Gera registro em `solicitacoes_aumento_limite.csv` com aprovação automática baseada no score do cliente vs. `score_limite.csv`.

**Critérios de aceite.**

- **Given** cliente autenticado com score 720 e limite atual R$ 5.000
- **When** solicita aumento para R$ 9.000
- **Then** sistema chama `solicitar_aumento_limite()`, grava no CSV com `status='aprovado'`, atualiza `limite_credito` no `clientes.csv` e responde confirmando

- **Given** cliente autenticado com score 450 (limite máximo R$ 2.000)
- **When** solicita aumento para R$ 5.000
- **Then** sistema grava no CSV com `status='rejeitado'` e oferece entrevista de crédito ao cliente

**Tasks relacionadas.** TASK-006, TASK-011, TASK-016.

### REQ-F-003 — Agente de Entrevista deve recalcular score

**Descrição.** Conduz entrevista financeira coletando 5 dados (renda, tipo de emprego, despesas, dependentes, dívidas), calcula novo score pela fórmula ponderada e atualiza `clientes.csv`.

**Fórmula obrigatória (do desafio):**

```python
score = (renda_mensal / (despesas + 1)) * 30
      + peso_emprego[tipo_emprego]            # formal=300, autonomo=200, desempregado=0
      + peso_dependentes[num_dependentes]     # 0=100, 1=80, 2=60, "3+"=30
      + peso_dividas[tem_dividas]             # sim=-100, não=+100
```

**Critérios de aceite.**

- **Given** cliente com renda R$ 5.000, formal, despesas R$ 1.500, 1 dependente, sem dívidas
- **When** conclui a entrevista
- **Then** novo score = `(5000/1501)*30 + 300 + 80 + 100 ≈ 580`, persiste em `clientes.csv`

- **Given** entrevista finalizada com sucesso
- **When** cliente concorda em tentar aumento novamente
- **Then** sistema redireciona para Agente de Crédito com novo score em contexto

**Tasks relacionadas.** TASK-007, TASK-012, TASK-017.

### REQ-F-004 — Agente de Câmbio deve consultar cotações em tempo real

**Descrição.** Consulta cotação atual de moedas estrangeiras (USD, EUR, GBP, BTC, JPY) via API externa e apresenta ao cliente formatado em Real.

**Critérios de aceite.**

- **Given** cliente solicita "qual o dólar hoje?"
- **When** sistema chama `consultar_cotacao("dolar")`
- **Then** retorna `{compra, venda, variacao_pct, timestamp}` e formata como "💱 Dólar Americano: Compra R$ X,XX | Venda R$ X,XX..."

**Tasks relacionadas.** TASK-008, TASK-013, TASK-018.

### REQ-F-005 — Transições entre agentes devem ser imperceptíveis ao cliente

**Descrição.** Conforme regra geral do desafio, o cliente deve perceber um único atendente. As tags ocultas (`[AUTH_OK]`, `[ROUTE|...]`) são removidas antes da exibição.

**Critérios de aceite.**

- **When** qualquer agente responde
- **Then** a resposta exibida ao cliente nunca contém colchetes `[...]`, nomes de agentes ou referências a "equipe"

**Tasks relacionadas.** TASK-014, TASK-020.

### REQ-F-006 — Encerramento gracioso a qualquer momento

**Descrição.** Se cliente solicitar fim do atendimento, sistema deve encerrar o loop e impedir novas mensagens.

**Critérios de aceite.**

- **Given** cliente envia "obrigado, pode encerrar"
- **When** Team processa a mensagem
- **Then** `session_state['encerrado'] = True` e UI bloqueia input

**Tasks relacionadas.** TASK-014, TASK-022.

### REQ-F-007 — Persistência de sessão entre turnos

**Descrição.** O contexto da conversa (autenticação, tentativas, score, etc.) deve persistir mesmo se o usuário recarregar a página Streamlit.

**Critérios de aceite.**

- **Given** cliente autenticou e iniciou solicitação de aumento
- **When** recarrega a página
- **Then** ao reabrir, sistema retoma do mesmo ponto via `session_id` armazenado em cookie

**Tasks relacionadas.** TASK-019, TASK-021.

### REQ-F-008 — Tratamento de erros controlado

**Descrição.** Conforme regra do desafio, erros (CSV inacessível, API de câmbio fora do ar, input inválido) devem ser tratados sem interromper a interação.

**Critérios de aceite.**

- **Given** AwesomeAPI retorna timeout
- **When** Agente de Câmbio recebe erro da tool
- **Then** responde "Serviço de cotação temporariamente indisponível, tente em instantes" e oferece outras ações

**Tasks relacionadas.** TASK-013, TASK-024.

---

## 4. Requisitos não-funcionais (REQ-NF)

| ID | Categoria | Requisito | Métrica de aceite |
|----|-----------|-----------|------------------|
| REQ-NF-001 | Performance | Latência p95 < 4s por turno | Medido via traces AgentOS |
| REQ-NF-002 | Performance | Instanciação de agente < 10ms | Garantido pelo Agno (~2µs nativo) |
| REQ-NF-003 | Custo | < R$ 0,05 por turno conversacional | Dashboard DeepInfra; tracking via spans |
| REQ-NF-004 | Custo | < US$ 25/mês infra Railway | Plano Hobby + Postgres |
| REQ-NF-005 | Disponibilidade | Uptime ≥ 99% (não-SLA) | Railway health checks |
| REQ-NF-006 | Segurança | Credenciais DeepInfra apenas em env vars | Sem hardcoded secrets; CI verifica |
| REQ-NF-007 | Segurança | JWT-based RBAC para acesso ao AgentOS | `JWT_VERIFICATION_KEY` no Railway |
| REQ-NF-008 | LGPD | CPF não logado em traces de produção | PII redaction via `pre_hooks` |
| REQ-NF-009 | LGPD | Dados de sessão criptografados em repouso | Postgres Railway com encryption-at-rest |
| REQ-NF-010 | Observabilidade | Todo run rastreável | AgentOS tracing nativo + UI os.agno.com |
| REQ-NF-011 | DX | Deploy em < 5 min após `git push` | Railway auto-deploy |
| REQ-NF-012 | DX | Setup local em < 10 min | `docker compose up -d --build` |
| REQ-NF-013 | Manutenibilidade | Todos os agentes seguem mesma estrutura | Lint check em CI |
| REQ-NF-014 | Manutenibilidade | Cobertura de testes ≥ 80% para tools | pytest-cov |
| REQ-NF-015 | Escalabilidade | Suportar 100 sessões concorrentes | Stateless runtime + Postgres pooling |

---

## 5. Arquitetura

### 5.1 Diagrama de componentes (alto nível)

```
┌──────────────────────────────────────────────────────────────────────┐
│                          CLIENTES                                    │
│                                                                      │
│   👤 Cliente final                       🛠️  CoE IA / Operador      │
│        │                                       │                     │
│        ▼                                       ▼                     │
│   ┌─────────────┐                       ┌──────────────────┐        │
│   │  Streamlit  │                       │   os.agno.com    │        │
│   │  (UI cliente)│                      │  (control plane) │        │
│   └──────┬──────┘                       └────────┬─────────┘        │
└──────────┼──────────────────────────────────────┼───────────────────┘
           │ HTTPS                                │ HTTPS + JWT
           │ POST /teams/banco-agil/runs          │ (read/write)
           ▼                                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  RAILWAY (production cloud)                          │
│                                                                      │
│   ┌────────────────────────────────────────────────────────────┐    │
│   │  AgentOS (FastAPI app, agno.os.AgentOS)                    │    │
│   │  ──────────────────────────────────────────────────────    │    │
│   │  • Team coordinator "Banco Ágil" (mode="coordinate")       │    │
│   │  • Members:                                                │    │
│   │    ├── Triagem Agent                                       │    │
│   │    ├── Crédito Agent                                       │    │
│   │    ├── Entrevista Agent                                    │    │
│   │    └── Câmbio Agent                                        │    │
│   │                                                            │    │
│   │  • Tools: auth, credit, interview, exchange                │    │
│   │  • Tracing nativo + JWT RBAC + 50+ endpoints REST/SSE      │    │
│   └────────────────────────┬───────────────────────────────────┘    │
│                            │                                         │
│                            ▼                                         │
│   ┌────────────────────────────────────────────────────────────┐    │
│   │  PostgreSQL + pgvector (Railway managed)                   │    │
│   │  Tabelas: sessions, memories, traces, knowledge, evals     │    │
│   └────────────────────────────────────────────────────────────┘    │
│                                                                      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ HTTPS
                               ▼
                  ┌──────────────────────────┐
                  │  DeepInfra API           │
                  │  (LLM inference)         │
                  │  • Qwen3-235B-Thinking   │
                  │  • DeepSeek-V3           │
                  └──────────────────────────┘
                               │
                               │ HTTPS (external)
                               ▼
                  ┌──────────────────────────┐
                  │  AwesomeAPI              │
                  │  (cotações câmbio)       │
                  └──────────────────────────┘
```

### 5.2 Fluxo de uma requisição completa

```
1. Cliente digita "Quero aumentar meu limite" no Streamlit
2. Streamlit POST → https://banco-agil-os.up.railway.app/teams/banco-agil/runs
   {message, session_id, user_id}
3. AgentOS recebe → carrega Team do Postgres → injeta session_state
4. Team coordinator decide: rotear para Crédito Agent
5. Crédito Agent → chama tool consultar_limite_credito(cpf=session_state['cpf'])
6. Tool lê clientes.csv (ou tabela Postgres em fase 2)
7. Crédito Agent gera resposta usando DeepInfra (Qwen3-235B-Thinking)
8. AgentOS persiste run trace no Postgres
9. Resposta volta para Streamlit (SSE streaming ou sync)
10. Streamlit renderiza com tags ocultas removidas
```

### 5.3 Estados de sessão

```python
session_state = {
    "autenticado":     bool,        # Auth completa?
    "cpf":             str | None,  # CPF do cliente (PII — não logar)
    "nome":            str | None,
    "score":           int | None,
    "limite_credito":  float | None,
    "tentativas_auth": int,         # 0–3
    "agente_ativo":    str,         # triagem | credito | entrevista | cambio
    "encerrado":       bool,
}
```

---

## 6. Decisões técnicas (ADRs)

### ADR-001 — Por que DeepInfra (e não OpenRouter, Groq, Bedrock)?

**Decisão.** Usar DeepInfra como provedor único de LLMs.

**Contexto.** O time CoE IA Cogna já tem stack DeepInfra validado (uso anterior: OpenClaw com roteamento DeepSeek V4-Flash + Qwen3-235B-Thinking). Conta corporativa já provisionada.

**Alternativas avaliadas.**

| Provedor | Custo | Modelos | Tool calling | Latência BR | Decisão |
|----------|------|---------|--------------|-------------|---------|
| DeepInfra | Baixo | Llama, Qwen, DeepSeek, Mistral | ✅ Excelente | ~400ms | **Escolhido** |
| OpenRouter | Médio (markup) | 200+ | ✅ Variável por modelo | ~500ms | Descartado (markup oculto) |
| Groq | Baixo | Llama, Mixtral | ✅ Bom | ~150ms (rápido!) | Descartado (catálogo menor) |
| AWS Bedrock | Médio-Alto | Claude, Nova, Llama | ✅ Excelente | ~300ms | Adiado (procurement Cogna) |

**Implicações.**

- Driver nativo: `from agno.models.deepinfra import DeepInfra` — Agno suporta DeepInfra como modelo nativo, e DeepInfra também aceita parâmetros do OpenAI.
- Variável de ambiente: `DEEPINFRA_API_KEY`.
- Sem dependência de `anthropic` ou `openai` no requirements.

### ADR-002 — Por que Railway (e não Render, Fly, AWS ECS)?

**Decisão.** Deployar o AgentOS no Railway.

**Contexto.** Agno publica template oficial `agno-agi/agentos-railway-template` com deploy `railway up` em 1 comando, Postgres + pgvector já provisionados.

**Alternativas avaliadas.**

| Plataforma | Setup | Custo (demo) | Postgres | Decisão |
|------------|-------|-------------|----------|---------|
| Railway | Template oficial Agno | ~US$ 10/mês | Managed + pgvector | **Escolhido** |
| Render | Manual | ~US$ 7/mês | Managed (sem pgvector nativo) | Descartado |
| Fly Machines | Manual + complexo | ~US$ 5/mês | Externo | Descartado |
| AWS ECS | Complexo + procurement Cogna | ~US$ 30/mês | RDS | Adiado para fase 2 |

### ADR-003 — Modo "coordinate" do Team (em vez de "route")

**Decisão.** Usar `Team(mode="coordinate")` ao invés de `mode="route"`.

**Contexto.** O fluxo Entrevista → Crédito (após recálculo de score) exige que o coordenador retenha o novo score e re-encaminhe ao Crédito sem reautenticar. Em modo `route`, o leader apenas decide um membro e retorna a resposta dele — não há encadeamento natural.

**Implicação.** O coordenador faz uma chamada LLM adicional por turno (a do leader). Trade-off aceitável dado a complexidade do fluxo.

### ADR-004 — Tags ocultas vs. structured output

**Decisão.** Manter o padrão `[AUTH_OK|...]` / `[ROUTE|...]` para comunicação coordenador↔membro.

**Contexto.** Modelos open-weight no DeepInfra (DeepSeek-V3, Qwen3) têm suporte variável a structured output em JSON nativo, dependendo da versão. Tags em texto são universais e baratas.

**Implicação.** Necessário regex robusto para parsing (`team.py::limpar_tags_da_resposta`).

### ADR-005 — Streamlit como UI cliente, os.agno.com como UI ops

**Decisão.** Manter Streamlit (exigência do desafio) + adicionar `os.agno.com` como ferramenta interna do CoE IA.

**Contexto.** Streamlit atende o requisito do desafio "UI simples para testes simulando atendimento". `os.agno.com` atende observabilidade, traces e gestão (REQ-NF-010).

### ADR-006 — Postgres + pgvector em vez de SQLite

**Decisão.** Storage de sessão e memória no PostgreSQL com extensão pgvector.

**Contexto.** AgentOS no Railway requer storage compartilhado entre instâncias (stateless runtime). SQLite quebra horizontal scaling.

**Implicação.** Provisionar plugin `pgvector` no Railway. Migrações automáticas via `SqliteDb` substituído por `PostgresDb` da Agno.

---

## 7. Stack tecnológica

### 7.1 Dependências Python (`pyproject.toml` / `requirements.txt`)

```toml
[project]
name = "banco-agil"
version = "1.0.0"
requires-python = ">=3.11"

dependencies = [
  "agno>=2.6.0",                # framework + AgentOS
  "openai>=1.50.0",             # SDK usado pelo driver DeepInfra (OpenAI-compatible)
  "fastapi>=0.115.0",           # base do AgentOS
  "uvicorn[standard]>=0.32.0",  # servidor ASGI
  "psycopg[binary,pool]>=3.2.0", # driver Postgres
  "pgvector>=0.3.0",            # extensão vector
  "pandas>=2.2.0",              # leitura/escrita CSV (fase 1)
  "httpx>=0.27.0",              # AwesomeAPI
  "python-dotenv>=1.0.0",       # .env
  "pydantic>=2.9.0",            # schemas
  "streamlit>=1.40.0",          # UI cliente
  "rich>=13.0.0",               # logs bonitos
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0.0",
  "pytest-asyncio>=0.24.0",
  "pytest-cov>=5.0.0",
  "ruff>=0.6.0",
  "mypy>=1.11.0",
]
```

### 7.2 Variáveis de ambiente (`example.env`)

```bash
# ── DeepInfra ────────────────────────────────────────────────────────────
DEEPINFRA_API_KEY=di_...                # OBRIGATÓRIO

# Modelos (configuração de cost/performance)
COORDINATOR_MODEL_ID=Qwen/Qwen3-235B-A22B-Thinking-2507
SPECIALIST_MODEL_ID=deepseek-ai/DeepSeek-V3-0324

# ── Banco de dados ──────────────────────────────────────────────────────
DB_URL=postgresql://user:pass@host:5432/banco_agil    # Railway provisiona

# ── AgentOS ─────────────────────────────────────────────────────────────
AGENTOS_URL=https://banco-agil-os.up.railway.app      # Railway domain público
AGENTOS_API_KEY=...                                    # Gerado em setup
JWT_VERIFICATION_KEY=-----BEGIN PUBLIC KEY-----...    # Para os.agno.com

# ── Aplicação ───────────────────────────────────────────────────────────
APP_ENV=production                # dev | staging | production
LOG_LEVEL=INFO                     # DEBUG | INFO | WARNING | ERROR
TELEMETRY_ENABLED=false            # Desabilitar telemetria Agno

# ── Streamlit (UI cliente) ──────────────────────────────────────────────
STREAMLIT_AGENTOS_URL=${AGENTOS_URL}    # mesma URL acima
STREAMLIT_API_KEY=${AGENTOS_API_KEY}    # mesma key

# ── APIs externas ───────────────────────────────────────────────────────
CAMBIO_API_URL=https://economia.awesomeapi.com.br/json/last/{pair}
# Sem chave necessária (API gratuita)
```

---

## 8. Modelo de dados

### 8.1 Tabelas Postgres (criadas pelo AgentOS)

```sql
-- Gerenciadas automaticamente pelo agno.db.postgres.PostgresDb
sessions          -- Histórico de runs por sessão (auto)
memories          -- User memories (auto)
traces            -- OpenTelemetry-like spans (auto)
knowledge         -- Embeddings pgvector (auto)
eval_runs         -- Resultados de evals (auto)
```

### 8.2 Tabelas de negócio (criadas por nós)

```sql
CREATE TABLE clientes (
    cpf              VARCHAR(11) PRIMARY KEY,
    data_nascimento  DATE NOT NULL,
    nome             VARCHAR(200) NOT NULL,
    score            INTEGER NOT NULL CHECK (score BETWEEN 0 AND 1000),
    limite_credito   NUMERIC(10, 2) NOT NULL,
    criado_em        TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE score_limite (
    score_minimo     INTEGER NOT NULL,
    score_maximo     INTEGER NOT NULL,
    limite_maximo    NUMERIC(10, 2) NOT NULL,
    PRIMARY KEY (score_minimo, score_maximo)
);

CREATE TABLE solicitacoes_aumento_limite (
    id                       BIGSERIAL PRIMARY KEY,
    cpf_cliente              VARCHAR(11) NOT NULL REFERENCES clientes(cpf),
    data_hora_solicitacao    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    limite_atual             NUMERIC(10, 2) NOT NULL,
    novo_limite_solicitado   NUMERIC(10, 2) NOT NULL,
    status_pedido            VARCHAR(20) NOT NULL CHECK (status_pedido IN ('pendente', 'aprovado', 'rejeitado')),
    score_no_momento         INTEGER
);

CREATE INDEX idx_sol_cpf ON solicitacoes_aumento_limite (cpf_cliente);
CREATE INDEX idx_sol_data ON solicitacoes_aumento_limite (data_hora_solicitacao DESC);
```

### 8.3 Estratégia de migração CSV → Postgres

| Fase | Estratégia | Justificativa |
|------|-----------|---------------|
| Fase 1 (MVP) | Manter CSV em `data/`, copiar para container | Compatível com desafio; rápido |
| Fase 2 | Seed Postgres com CSV no deploy | Suporta horizontal scaling |
| Fase 3 | UI admin para gestão de clientes | Operação real |

Para o MVP, a tool `_atualizar_limite_no_csv()` permanece, mas em Fase 2 vira `_atualizar_limite_no_db()` lendo do Postgres.

---

## 9. Especificação dos agentes

### 9.1 Padrão de definição

Cada agente segue o template:

```python
from agno.agent import Agent
from agno.models.deepinfra import DeepInfra
from banco_agil.config import SPECIALIST_MODEL_ID

agente = Agent(
    name="<Nome do Agente>",
    role="<Descrição curta do papel>",
    model=DeepInfra(id=SPECIALIST_MODEL_ID),
    tools=[<lista de funções Python>],
    instructions=[
        # 1. Identidade e comportamento
        # 2. Fluxo principal
        # 3. Tratamento de erros
        # 4. Tags de saída
        # 5. Restrições
    ],
    add_history_to_context=True,
    num_history_runs=5,
    markdown=True,
)
```

### 9.2 Agente de Triagem

| Campo | Valor |
|-------|-------|
| `name` | "Agente de Triagem" |
| `role` | Autenticação e direcionamento inicial |
| `model` | `DeepInfra(id=SPECIALIST_MODEL_ID)` |
| `tools` | `autenticar_cliente`, `buscar_dados_cliente` |
| `num_history_runs` | 5 |

**Instruções-chave.**
- Saudar e solicitar CPF, depois data de nascimento.
- Chamar `autenticar_cliente(cpf, data_nascimento)` quando ambos disponíveis.
- Emitir `[AUTH_OK|cpf=X|nome=Y|score=Z|limite=W]` se sucesso.
- Emitir `[AUTH_FAIL]` se falha.
- Identificar assunto pós-auth e emitir `[ROUTE|credito]` ou `[ROUTE|cambio]`.

### 9.3 Agente de Crédito

| Campo | Valor |
|-------|-------|
| `name` | "Agente de Crédito" |
| `role` | Consulta limite, processa aumento |
| `model` | `DeepInfra(id=SPECIALIST_MODEL_ID)` |
| `tools` | `consultar_limite_credito`, `verificar_limite_pelo_score`, `solicitar_aumento_limite` |
| `num_history_runs` | 5 |

**Instruções-chave.**
- Receber CPF do `session_state`.
- Consulta de limite: chamar `consultar_limite_credito(cpf)` e apresentar formatado.
- Aumento: chamar `solicitar_aumento_limite(cpf, novo_limite)`.
- Se rejeitado: oferecer entrevista → `[ROUTE|entrevista]`.
- Formatar valores como `R$ X.XXX,XX`.

### 9.4 Agente de Entrevista

| Campo | Valor |
|-------|-------|
| `name` | "Agente de Entrevista de Crédito" |
| `role` | Coleta dados, recalcula score |
| `model` | `DeepInfra(id=COORDINATOR_MODEL_ID)` — usa modelo mais forte (raciocínio + cálculo) |
| `tools` | `calcular_score_credito`, `atualizar_score_cliente` |
| `num_history_runs` | 8 |

**Instruções-chave.**
- Coletar 5 informações **uma de cada vez**, em ordem natural (renda, emprego, despesas, dependentes, dívidas).
- Após todas coletadas: chamar `calcular_score_credito(...)`, depois `atualizar_score_cliente(cpf, novo_score)`.
- Comunicar resultado: parabenizar se melhorou, sugerir ações se piorou.
- Emitir `[ROUTE|credito|score_atualizado=X]` se cliente quer tentar aumento.

### 9.5 Agente de Câmbio

| Campo | Valor |
|-------|-------|
| `name` | "Agente de Câmbio" |
| `role` | Cotação em tempo real |
| `model` | `DeepInfra(id=SPECIALIST_MODEL_ID)` |
| `tools` | `consultar_cotacao`, `listar_moedas_suportadas` |
| `num_history_runs` | 3 |

**Instruções-chave.**
- Identificar moeda na pergunta (português ou ISO).
- Chamar `consultar_cotacao(moeda)`.
- Apresentar: compra, venda, variação %, timestamp.
- Se moeda não suportada: listar opções via `listar_moedas_suportadas()`.

### 9.6 Team coordinator "Banco Ágil"

| Campo | Valor |
|-------|-------|
| `name` | "Banco Ágil" |
| `mode` | `"coordinate"` |
| `model` | `DeepInfra(id=COORDINATOR_MODEL_ID)` |
| `members` | `[triagem_agent, credito_agent, entrevista_agent, cambio_agent]` |
| `db` | `PostgresDb(db_url=DB_URL)` |
| `session_state` | dict inicial (ver Seção 5.3) |
| `add_history_to_context` | `True` |
| `add_session_state_to_context` | `True` |
| `num_history_runs` | 10 |
| `show_members_responses` | `False` (não vazar handoffs) |

**Instruções-chave.**
- Verificar `session_state['autenticado']` antes de qualquer ação.
- Se `tentativas_auth >= 3`: encerrar.
- Processar tags `[AUTH_OK]`, `[AUTH_FAIL]`, `[ROUTE|...]` atualizando `session_state`.
- Nunca expor tags ao cliente.

---

## 10. Especificação das ferramentas (tools)

> Cada tool é uma função Python pura. Type hints obrigatórios — Agno gera o JSON Schema automaticamente para function calling.

### 10.1 `auth_tools.py`

#### `autenticar_cliente(cpf: str, data_nascimento: str) -> dict`

| Campo | Especificação |
|-------|--------------|
| Inputs | `cpf` (any format), `data_nascimento` (DD/MM/YYYY ou ISO) |
| Output | `{sucesso: bool, mensagem: str, dados_cliente: dict | None}` |
| Side effects | Nenhum (leitura) |
| Errores possíveis | Base indisponível → retorna `sucesso=False` com mensagem |

#### `buscar_dados_cliente(cpf: str) -> dict | None`

| Campo | Especificação |
|-------|--------------|
| Inputs | `cpf` (apenas dígitos) |
| Output | `{cpf, nome, score, limite_credito} | None` |

### 10.2 `credit_tools.py`

#### `consultar_limite_credito(cpf: str) -> dict`

| Campo | Especificação |
|-------|--------------|
| Inputs | `cpf` |
| Output | `{nome, cpf, score, limite_atual} | {erro: str}` |

#### `verificar_limite_pelo_score(score: int, novo_limite: float) -> dict`

| Campo | Especificação |
|-------|--------------|
| Inputs | `score` (0–1000), `novo_limite` (R$) |
| Output | `{elegivel: bool, limite_maximo_permitido: float, faixa_score: str}` |

#### `solicitar_aumento_limite(cpf: str, novo_limite: float) -> dict`

| Campo | Especificação |
|-------|--------------|
| Inputs | `cpf`, `novo_limite` |
| Output | `{status: 'aprovado' | 'rejeitado' | 'erro', limite_atual, novo_limite_solicitado, limite_maximo_permitido?, score?, mensagem}` |
| Side effects | Grava em `solicitacoes_aumento_limite.csv`; se aprovado, atualiza `clientes.csv` |
| Errors | Falha I/O → retorna `status='erro'` |

### 10.3 `interview_tools.py`

#### `calcular_score_credito(renda_mensal, tipo_emprego, despesas_fixas_mensais, num_dependentes, tem_dividas) -> dict`

| Campo | Especificação |
|-------|--------------|
| Inputs | `renda_mensal: float`, `tipo_emprego: Literal["formal","autonomo","autônomo","desempregado"]`, `despesas_fixas_mensais: float`, `num_dependentes: int`, `tem_dividas: Literal["sim","nao","não"]` |
| Output | `{score: int (0–1000), detalhamento: dict}` |
| Validação | Tipos inválidos retornam `{erro: str}` |

#### `atualizar_score_cliente(cpf: str, novo_score: int) -> dict`

| Campo | Especificação |
|-------|--------------|
| Output | `{sucesso, score_anterior, score_novo, mensagem}` |
| Side effects | Atualiza `clientes.csv` linha correspondente |

### 10.4 `exchange_tools.py`

#### `consultar_cotacao(moeda: str) -> dict`

| Campo | Especificação |
|-------|--------------|
| Inputs | `moeda` (português ou ISO: "dolar", "USD", "euro", "EUR", etc.) |
| Output | `{moeda, par, compra, venda, variacao_pct, timestamp, fonte} | {erro: str}` |
| External | `GET https://economia.awesomeapi.com.br/json/last/{pair}` (sem auth) |
| Timeout | 8 segundos |

#### `listar_moedas_suportadas() -> list[str]`

| Campo | Especificação |
|-------|--------------|
| Output | `["USD-BRL", "EUR-BRL", "GBP-BRL", "BTC-BRL", "JPY-BRL"]` |

---

## 11. Contratos de API (AgentOS)

> O AgentOS expõe automaticamente 50+ endpoints REST/SSE. Documentamos os principais que a UI Streamlit consome.

### 11.1 Endpoint principal: executar um turno

```http
POST /teams/{team_id}/runs
Authorization: Bearer <AGENTOS_API_KEY>
Content-Type: application/json

{
  "message": "Quero aumentar meu limite",
  "session_id": "uuid-gerado-pelo-streamlit",
  "user_id": "anonymous",
  "stream": false
}
```

**Resposta (síncrona).**

```json
{
  "run_id": "run_abc123",
  "session_id": "uuid-gerado-pelo-streamlit",
  "content": "Claro! Vou ajudar com isso. Seu limite atual é R$ 5.000,00...",
  "metrics": {
    "tokens": {"input": 1200, "output": 180, "total": 1380},
    "duration_ms": 2340
  }
}
```

**Resposta (streaming SSE).** Quando `stream=true`, retorna chunks `data: {...}` event-stream.

### 11.2 Endpoint de sessão

```http
GET /sessions/{session_id}
GET /sessions/{session_id}/messages
DELETE /sessions/{session_id}
```

### 11.3 Health check

```http
GET /health
→ 200 OK {"status": "healthy", "version": "1.0.0"}
```

### 11.4 Documentação interativa

```
GET /docs              → Swagger UI (autogerado pelo FastAPI)
GET /openapi.json      → OpenAPI spec
```

---

## 12. Configuração de modelos (DeepInfra)

### 12.1 Estratégia de roteamento (cost-aware)

Seguindo o padrão validado no OpenClaw (DeepSeek + Qwen3-Thinking):

| Componente | Modelo | Por quê |
|------------|--------|---------|
| **Team Coordinator** | `Qwen/Qwen3-235B-A22B-Thinking-2507` | Raciocínio para decidir routing e processar tags; vale o custo extra |
| **Entrevista Agent** | `Qwen/Qwen3-235B-A22B-Thinking-2507` | Raciocínio para cálculo de score e empatia |
| **Triagem Agent** | `deepseek-ai/DeepSeek-V3-0324` | Extração simples (CPF, data); barato |
| **Crédito Agent** | `deepseek-ai/DeepSeek-V3-0324` | Tool calling + formatação; barato |
| **Câmbio Agent** | `deepseek-ai/DeepSeek-V3-0324` | Tool calling simples; barato |

> **Validação de seleção.** No início do projeto, validar que ambos os modelos suportam `function_calling` no DeepInfra. Em caso de incompatibilidade, fallback para `meta-llama/Meta-Llama-3.3-70B-Instruct` (estável, function-calling consistente).

### 12.2 Padrão de inicialização

```python
# config.py
import os
from agno.models.deepinfra import DeepInfra

COORDINATOR_MODEL_ID = os.getenv(
    "COORDINATOR_MODEL_ID",
    "Qwen/Qwen3-235B-A22B-Thinking-2507",
)
SPECIALIST_MODEL_ID = os.getenv(
    "SPECIALIST_MODEL_ID",
    "deepseek-ai/DeepSeek-V3-0324",
)

def get_coordinator_model() -> DeepInfra:
    return DeepInfra(
        id=COORDINATOR_MODEL_ID,
        temperature=0.3,           # Baixa para consistência em routing
        max_tokens=2000,
    )

def get_specialist_model() -> DeepInfra:
    return DeepInfra(
        id=SPECIALIST_MODEL_ID,
        temperature=0.5,           # Média para resposta natural
        max_tokens=1500,
    )
```

### 12.3 Estimativa de custos

| Modelo | Input ($/M) | Output ($/M) | Tokens médios/turno | Custo/turno |
|--------|-------------|--------------|--------------------|-----|
| Qwen3-235B-Thinking | $0.30 | $1.20 | 1.5K in + 0.4K out | $0.0009 |
| DeepSeek-V3-0324 | $0.14 | $0.28 | 1.2K in + 0.3K out | $0.00025 |

**Projeção mensal (1000 sessões × 8 turnos):**
- Coordinator + Entrevista (~30% dos turnos): 2400 × $0.0009 = **$2.16**
- Specialists (~70%): 5600 × $0.00025 = **$1.40**
- **Total: ~$3.56/mês LLM** — folga enorme vs. REQ-NF-003 (R$ 0,05/turno).

---

## 13. Estrutura de diretórios alvo

```
banco-agil/
├── app/                              # AgentOS application (NEW)
│   ├── __init__.py
│   ├── main.py                       # AgentOS entry point (FastAPI)
│   └── config.yaml                   # Configs do AgentOS (quick prompts, etc.)
│
├── banco_agil/                       # Domínio (REUSE do scaffold)
│   ├── __init__.py
│   ├── config.py                     # ⚠️ ALTERADO: DeepInfra + Postgres
│   ├── team.py                       # ⚠️ ALTERADO: PostgresDb, modelos DeepInfra
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── triagem.py                # ⚠️ ALTERADO: model=DeepInfra
│   │   ├── credito.py                # ⚠️ ALTERADO: model=DeepInfra
│   │   ├── entrevista.py             # ⚠️ ALTERADO: model=DeepInfra
│   │   └── cambio.py                 # ⚠️ ALTERADO: model=DeepInfra
│   └── tools/                        # SEM ALTERAÇÃO (já são funções puras)
│       ├── __init__.py
│       ├── auth_tools.py
│       ├── credit_tools.py
│       ├── interview_tools.py
│       └── exchange_tools.py
│
├── data/                             # CSVs do desafio (mantidos)
│   ├── clientes.csv
│   ├── score_limite.csv
│   └── solicitacoes_aumento_limite.csv      # gerado em runtime
│
├── evals/                            # Test suite (NEW)
│   ├── __init__.py
│   ├── __main__.py                   # Runner: `python -m evals`
│   └── cases.py                      # Declarative test cases (AgentAsJudgeEval)
│
├── tests/                            # Unit tests (NEW)
│   ├── __init__.py
│   ├── test_auth_tools.py
│   ├── test_credit_tools.py
│   ├── test_interview_tools.py
│   ├── test_exchange_tools.py
│   └── test_team.py
│
├── ui/                               # Streamlit UI (REORGANIZADO)
│   ├── streamlit_app.py              # ⚠️ ALTERADO: consume AgentOS REST
│   └── api_client.py                 # NEW: HTTP client p/ AgentOS
│
├── docs/                             # Documentação (NEW)
│   ├── SDD.md                        # Este documento
│   ├── README.md                     # Setup local
│   └── runbook.md                    # Operação produção
│
├── scripts/                          # Helpers de deploy (NEW)
│   ├── railway_up.sh                 # Deploy script
│   ├── seed_db.py                    # Migra CSV → Postgres
│   └── load_skill.sh                 # Instala Agno Skill no Claude Code
│
├── Dockerfile                        # NEW: container do AgentOS
├── docker-compose.yml                # NEW: stack local (AgentOS + Postgres)
├── railway.json                      # NEW: config do Railway
├── pyproject.toml                    # NEW: dependências modernas
├── example.env                       # ⚠️ ALTERADO: variáveis DeepInfra + Railway
├── AGENTS.md                         # NEW: instruções p/ Claude Code
└── README.md                         # ⚠️ ALTERADO: refletir nova arquitetura
```

---

## 14. Delta vs. scaffold atual

> Arquivos do scaffold inicial que precisam ser modificados ou criados.

### 14.1 Arquivos a ALTERAR

| Arquivo | Mudança | Risco |
|---------|---------|-------|
| `banco_agil/config.py` | `MODEL_ID` → `COORDINATOR_MODEL_ID` + `SPECIALIST_MODEL_ID`; remover `SESSION_DB`; adicionar `DB_URL` | Baixo |
| `banco_agil/team.py` | `Claude` → `DeepInfra`; `SqliteDb` → `PostgresDb` | Médio |
| `banco_agil/agents/*.py` (4 arquivos) | `from agno.models.anthropic import Claude` → `from agno.models.deepinfra import DeepInfra` | Baixo |
| `requirements.txt` | Remover `anthropic`; adicionar `psycopg`, `pgvector`, `openai` (transitivo) | Baixo |
| `app.py` (raiz) | Mover para `ui/streamlit_app.py`; chamar API REST do AgentOS | Médio |
| `.env.example` | Trocar `ANTHROPIC_API_KEY` por `DEEPINFRA_API_KEY` + variáveis Railway | Baixo |
| `README.md` | Refletir nova stack | Baixo |

### 14.2 Arquivos a CRIAR

| Arquivo | Propósito |
|---------|-----------|
| `app/main.py` | Entry point AgentOS (FastAPI) |
| `app/config.yaml` | Quick prompts do AgentOS UI |
| `Dockerfile` | Container image |
| `docker-compose.yml` | Stack local AgentOS + Postgres |
| `railway.json` | Config Railway (CPU/mem, build) |
| `pyproject.toml` | Substituir requirements.txt |
| `evals/cases.py` | Test cases declarativos |
| `evals/__main__.py` | Runner de evals |
| `tests/test_*.py` | Unit tests pytest |
| `ui/api_client.py` | HTTP client para AgentOS |
| `scripts/seed_db.py` | Migra CSVs para Postgres |
| `scripts/railway_up.sh` | Deploy automatizado |
| `AGENTS.md` | Guia para Claude Code |
| `docs/runbook.md` | Operação produção |

### 14.3 Arquivos a REMOVER

| Arquivo | Por quê |
|---------|---------|
| `tmp/banco_agil.db` (SQLite) | Storage agora é Postgres |
| `app.py` (raiz, será movido) | Migrado para `ui/streamlit_app.py` |

---

## 15. Plano de implementação (tasks para Claude Code)

> Tasks atômicas ordenadas por dependência. Cada uma referencia REQ-F/REQ-NF e arquivos. Use checkboxes `- [ ]` para track no Claude Code.

### Fase 1: Migração de modelo (DeepInfra)

- [ ] **TASK-001** — Atualizar `pyproject.toml` com dependências da Seção 7.1; remover `anthropic` se presente
  - **Aceite.** `pip install -e .` instala sem erros; `python -c "from agno.models.deepinfra import DeepInfra"` funciona.

- [ ] **TASK-002** — Atualizar `banco_agil/config.py`
  - Adicionar `COORDINATOR_MODEL_ID`, `SPECIALIST_MODEL_ID` lendo de env
  - Adicionar `DB_URL` lendo de env
  - Remover `SESSION_DB`
  - Adicionar `get_coordinator_model()` e `get_specialist_model()` (ver Seção 12.2)
  - **Aceite.** `python -c "from banco_agil.config import get_coordinator_model; print(get_coordinator_model())"` (com `DEEPINFRA_API_KEY` mock) imprime o objeto.

- [ ] **TASK-003** — Substituir `Claude` por `DeepInfra` em todos os 4 agentes
  - `agents/triagem.py`, `agents/credito.py`, `agents/cambio.py` → usam `get_specialist_model()`
  - `agents/entrevista.py` → usa `get_coordinator_model()`
  - **Aceite.** `grep -r "anthropic" banco_agil/` retorna vazio.

- [ ] **TASK-004** — Atualizar `banco_agil/team.py`
  - Substituir `SqliteDb` por `PostgresDb` (`from agno.db.postgres import PostgresDb`)
  - Trocar `Claude` por `get_coordinator_model()`
  - Adicionar `db_url=DB_URL` ao `PostgresDb`
  - **Aceite.** `from banco_agil.team import criar_equipe; criar_equipe("test")` instancia sem erro (com env vars válidas).

### Fase 2: AgentOS App

- [ ] **TASK-005** — Criar `app/main.py`
  ```python
  from agno.os import AgentOS
  from banco_agil.team import criar_equipe_factory

  team = criar_equipe_factory()  # versão que retorna Team singleton
  agent_os = AgentOS(
      name="Banco Ágil",
      teams=[team],
      scheduler=True,
      tracing=True,
  )
  app = agent_os.get_app()
  ```
  - **Aceite.** `uvicorn app.main:app --reload` sobe na porta 8000; `GET /docs` mostra Swagger; `GET /health` retorna 200.

- [ ] **TASK-006** — Criar `app/config.yaml` com quick prompts
  ```yaml
  quick_prompts:
    - "Quero consultar meu limite"
    - "Quero aumentar meu limite"
    - "Qual a cotação do dólar?"
  ```
  - **Aceite.** Quick prompts aparecem na UI `os.agno.com` após conexão.

- [ ] **TASK-007** — Criar `Dockerfile`
  ```dockerfile
  FROM python:3.11-slim
  WORKDIR /app
  COPY pyproject.toml .
  RUN pip install --no-cache-dir -e .
  COPY . .
  EXPOSE 8000
  CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```
  - **Aceite.** `docker build -t banco-agil .` completa sem erros.

- [ ] **TASK-008** — Criar `docker-compose.yml` com Postgres + pgvector
  ```yaml
  services:
    agent-os:
      build: .
      ports: ["8000:8000"]
      env_file: .env
      depends_on: [postgres]
    postgres:
      image: ankane/pgvector:latest
      environment:
        POSTGRES_USER: banco
        POSTGRES_PASSWORD: agil
        POSTGRES_DB: banco_agil
      volumes: ["pgdata:/var/lib/postgresql/data"]
      ports: ["5432:5432"]
  volumes: {pgdata: {}}
  ```
  - **Aceite.** `docker compose up -d --build` levanta os 2 containers; `curl localhost:8000/health` retorna 200.

### Fase 3: UI Streamlit refatorada

- [ ] **TASK-009** — Criar `ui/api_client.py`
  ```python
  import httpx, uuid
  from banco_agil.config import AGENTOS_URL, AGENTOS_API_KEY

  class BancoAgilClient:
      def __init__(self):
          self.client = httpx.Client(
              base_url=AGENTOS_URL,
              headers={"Authorization": f"Bearer {AGENTOS_API_KEY}"},
              timeout=30.0,
          )
      def run(self, team_id: str, message: str, session_id: str) -> dict:
          r = self.client.post(
              f"/teams/{team_id}/runs",
              json={"message": message, "session_id": session_id},
          )
          r.raise_for_status()
          return r.json()
  ```
  - **Aceite.** Pytest com mock do AgentOS retorna dict válido.

- [ ] **TASK-010** — Refatorar `ui/streamlit_app.py`
  - Remove `from banco_agil.team import criar_equipe`
  - Usa `BancoAgilClient` para chamar `/teams/banco-agil/runs`
  - Lógica de tags ocultas permanece
  - **Aceite.** `streamlit run ui/streamlit_app.py` (com AgentOS rodando local) executa autenticação end-to-end.

### Fase 4: Database seed

- [ ] **TASK-011** — Criar `scripts/seed_db.py`
  - Conecta ao Postgres via `DB_URL`
  - Cria tabelas (DDL da Seção 8.2)
  - Lê `data/clientes.csv` e `data/score_limite.csv`
  - INSERT com `ON CONFLICT DO UPDATE`
  - **Aceite.** `python scripts/seed_db.py` executado contra Postgres local popula 5 clientes e 6 faixas de score.

- [ ] **TASK-012** — (Opcional Fase 1) Refatorar tools para ler do Postgres em vez de CSV
  - Apenas se tempo permitir; senão postergar para fase 2
  - **Aceite.** Tests passam com `pytest tests/test_credit_tools.py` apontando para Postgres.

### Fase 5: Tests + Evals

- [ ] **TASK-013** — Criar `tests/test_auth_tools.py`, `test_credit_tools.py`, `test_interview_tools.py`, `test_exchange_tools.py`
  - Cobrir happy path + edge cases (CPF inválido, score borderline, API timeout)
  - Mock HTTP para AwesomeAPI (`pytest-httpx` ou `respx`)
  - **Aceite.** `pytest tests/ -v --cov=banco_agil/tools --cov-fail-under=80`.

- [ ] **TASK-014** — Criar `evals/cases.py` com `AgentAsJudgeEval`
  ```python
  from agno.eval.agent_as_judge import AgentAsJudgeEval

  cases = [
      AgentAsJudgeEval(
          name="auth_happy_path",
          team=team,
          prompts=["Oi", "12345678901", "15/05/1990"],
          rubric="Autenticou Ana Oliveira sem expor agentes internos",
      ),
      AgentAsJudgeEval(
          name="aumento_aprovado",
          ...
      ),
      AgentAsJudgeEval(
          name="rejeicao_oferece_entrevista",
          ...
      ),
      AgentAsJudgeEval(
          name="entrevista_recalcula_score",
          ...
      ),
      AgentAsJudgeEval(
          name="cambio_dolar",
          ...
      ),
      AgentAsJudgeEval(
          name="bloqueio_3_tentativas",
          ...
      ),
  ]
  ```
  - **Aceite.** `python -m evals` executa 6 casos, log no Postgres, ≥90% pass rate.

### Fase 6: Deploy Railway

- [ ] **TASK-015** — Criar `railway.json`
  ```json
  {
    "build": {"builder": "DOCKERFILE"},
    "deploy": {
      "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
      "healthcheckPath": "/health",
      "restartPolicyType": "ON_FAILURE",
      "restartPolicyMaxRetries": 3
    }
  }
  ```
  - **Aceite.** Railway detecta o config no `railway up`.

- [ ] **TASK-016** — Criar `scripts/railway_up.sh`
  ```bash
  #!/bin/bash
  set -e
  railway login
  railway init banco-agil
  railway add postgresql
  railway add --plugin pgvector
  railway variables set $(cat .env.production | xargs)
  railway up
  echo "Deploy em: $(railway domain)"
  ```
  - **Aceite.** Script executa fim-a-fim; domínio público responde `GET /health`.

- [ ] **TASK-017** — Configurar JWT no Railway
  - Gerar par RSA: `openssl genrsa -out private.pem 2048 && openssl rsa -in private.pem -pubout -out public.pem`
  - Setar `JWT_VERIFICATION_KEY` no Railway com o conteúdo de `public.pem`
  - **Aceite.** Após restart, `os.agno.com` consegue conectar via "Add OS → Live" com JWT.

- [ ] **TASK-018** — Conectar `os.agno.com` ao AgentOS Railway
  - Login `os.agno.com` → Add OS → Live → URL Railway → autenticar
  - **Aceite.** Chat funciona; traces aparecem em tempo real.

### Fase 7: Documentação e governança

- [ ] **TASK-019** — Atualizar `README.md` raiz
  - Refletir nova arquitetura (Railway, DeepInfra, os.agno.com)
  - Quickstart: clone → docker compose → seed → streamlit
  - **Aceite.** Pessoa nova no projeto consegue rodar em < 10 min seguindo README.

- [ ] **TASK-020** — Criar `AGENTS.md` para Claude Code
  ```markdown
  # Instruções para Claude Code

  Este projeto é o Banco Ágil — atendimento bancário multi-agente em Agno.

  ## Quando perguntarem para criar/editar um agente:
  1. Edite o arquivo correspondente em `banco_agil/agents/`
  2. Mantenha o padrão de instructions (5 seções)
  3. Use `get_specialist_model()` por padrão; `get_coordinator_model()` apenas se exigir raciocínio
  4. Registre no `banco_agil/team.py::criar_equipe()` se for novo
  5. Adicione eval em `evals/cases.py`

  ## Comandos de teste:
  - `pytest tests/` — unit tests
  - `python -m evals` — evals com judge
  - `docker compose up -d` — stack local
  ```
  - **Aceite.** Claude Code lê e segue o padrão ao criar novos agentes.

- [ ] **TASK-021** — Criar `docs/runbook.md` (operação)
  - Como ver traces no `os.agno.com`
  - Como rotacionar `DEEPINFRA_API_KEY`
  - Como restaurar backup do Postgres
  - Como rollback via Railway
  - **Aceite.** CoE IA consegue diagnosticar incident usando o runbook.

### Fase 8: Skill Agno no Claude Code

- [ ] **TASK-022** — Instalar Agno Skill no Claude Code
  ```bash
  npx skills add agno-agi/agno-skills --skill agno
  ```
  - **Aceite.** Claude Code reconhece padrões Agno em prompts e gera código compatível.

- [ ] **TASK-023** — Adicionar Agno Docs como MCP server no Claude Code
  ```bash
  claude mcp add --transport http agno-docs https://docs.agno.com/mcp
  ```
  - **Aceite.** Claude Code pode buscar docs do Agno on-the-fly durante desenvolvimento.

---

## 16. Testes e evals

### 16.1 Estratégia em pirâmide

```
        ┌──────────────────────────┐
        │  Evals (AgentAsJudge)    │  ← 6 casos cobrindo fluxos críticos
        │  Lentos · alta confiança │
        └──────────────────────────┘
              ┌────────────────────────┐
              │  Integration (httpx)   │  ← UI ↔ AgentOS REST
              │  Médios                │
              └────────────────────────┘
                    ┌──────────────────────────┐
                    │  Unit (pytest)           │  ← Tools, parsing, schemas
                    │  Rápidos · alto volume   │
                    └──────────────────────────┘
```

### 16.2 Casos de eval obrigatórios

| ID | Cenário | Critério de aprovação |
|----|---------|----------------------|
| EV-001 | Auth happy path | Autentica Ana sem expor agentes |
| EV-002 | Auth fail 3 vezes | Bloqueia + mensagem cordial |
| EV-003 | Consulta limite | Retorna limite correto formatado |
| EV-004 | Aumento aprovado | Status aprovado + CSV atualizado |
| EV-005 | Aumento rejeitado + entrevista | Oferece entrevista; após entrevista, retoma crédito |
| EV-006 | Cotação dólar | Retorna valores plausíveis (R$ 4-7) |
| EV-007 | Transição imperceptível | Em nenhuma resposta há `[`, `]`, "agente" ou "equipe" |
| EV-008 | Encerramento voluntário | "Obrigado, encerrar" finaliza sessão |

### 16.3 Comandos

```bash
# Unit tests
pytest tests/ -v --cov=banco_agil --cov-report=term

# Evals (requer DEEPINFRA_API_KEY válida)
python -m evals                           # roda tudo
python -m evals --case auth_happy_path    # caso isolado
python -m evals -v                        # streaming verbose

# Lint + type check
ruff check banco_agil/ app/ tests/
mypy banco_agil/
```

---

## 17. Deploy e operação

### 17.1 Ambiente local (dev)

```bash
# 1. Clone e setup
git clone https://github.com/<org>/banco-agil.git
cd banco-agil
cp example.env .env
# Editar .env com DEEPINFRA_API_KEY

# 2. Stack local
docker compose up -d --build
docker compose exec agent-os python scripts/seed_db.py

# 3. AgentOS rodando em http://localhost:8000
curl http://localhost:8000/health
# Abrir Swagger: http://localhost:8000/docs

# 4. Conectar ao os.agno.com (UI)
# Login → Add OS → Local → http://localhost:8000 → Connect

# 5. UI Streamlit
streamlit run ui/streamlit_app.py
# http://localhost:8501
```

### 17.2 Deploy produção (Railway)

```bash
# Pré-requisito: railway CLI instalado
# https://docs.railway.app/develop/cli

bash scripts/railway_up.sh

# Output esperado:
# [✓] Projeto criado: banco-agil
# [✓] PostgreSQL provisionado com pgvector
# [✓] Container deployado: banco-agil.up.railway.app
# [✓] Domínio público: https://banco-agil-production.up.railway.app
```

### 17.3 Conectar Streamlit produção ao AgentOS Railway

```bash
# Em .env (local ou Streamlit Cloud)
export AGENTOS_URL=https://banco-agil-production.up.railway.app
export AGENTOS_API_KEY=<key gerada em os.agno.com>

streamlit run ui/streamlit_app.py
```

### 17.4 Pipeline CI/CD (sugerido)

```yaml
# .github/workflows/deploy.yml
name: Deploy to Railway
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -e ".[dev]"
      - run: pytest tests/
      - run: ruff check banco_agil/
  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: railwayapp/cli-action@v2
        with:
          api-token: ${{ secrets.RAILWAY_TOKEN }}
      - run: railway up --service banco-agil
```

---

## 18. Observabilidade e governança CoE IA

### 18.1 Tracing

AgentOS produz spans nativos para:
- Cada turn de conversa (run_id, session_id, duration_ms, tokens)
- Cada chamada de LLM (model, latency, input/output tokens, cost estimate)
- Cada chamada de tool (tool_name, args, result, error)

Visualização: `os.agno.com → Traces`.

### 18.2 Métricas operacionais (a coletar)

| Métrica | SLO | Como medir |
|---------|-----|------------|
| Latência p95 por turn | < 4s | Span `total_duration_ms` |
| Taxa de erro de tool | < 1% | Span `tool_error_count / tool_call_count` |
| Custo médio por turn | < R$ 0,05 | Cost estimate da Agno + multiplicador BRL |
| Sessões com auth bem-sucedida | ≥ 70% | Count session_state['autenticado']=True |
| Taxa de rejeição em aumento | (observar) | Count `status='rejeitado'` em solicitações |
| Sessões redirecionadas para entrevista | (observar) | Count tag `[ROUTE|entrevista]` |

### 18.3 Alinhamento CoE IA Cogna

| Item da governança | Estado |
|---------------------|--------|
| Política de IA Cogna aprovada pelo Board | ⚠️ Gap conhecido (ESG B3/Dow Jones) — comunicar a aplicação |
| Homologação no Marketplace CoE IA | Aplicação registrada com status "em piloto" |
| Guardrails G1–G4 | G1 (PII): CPF não logado; G2 (output): sem invenção de dados; G3 (escopo): apenas crédito/câmbio; G4 (escalation): bloqueio após 3 falhas |
| LGPD — DSR | Tool admin para deletar sessão e clientes por CPF |
| LGPD — minimização | Apenas CPF + data + nome + score são processados |
| Auditoria | Traces AgentOS retidos por 90 dias no Postgres Railway |

### 18.4 Custos sob controle

- Dashboard DeepInfra: alerta em $20/mês
- Dashboard Railway: alerta em $30/mês
- Total budget: < $50/mês para piloto

---

## 19. Roadmap pós-MVP

### Sprint 2 (após MVP em produção)
- [ ] Migrar leitura/escrita de CSV para Postgres (tabelas da Seção 8.2)
- [ ] Adicionar Slack interface (Agno suporta nativo)
- [ ] Implementar PII redaction via `pre_hooks` (REQ-NF-008)

### Sprint 3
- [ ] Streamlit hospedado em Streamlit Cloud (ou Vercel)
- [ ] Autenticação OAuth no Streamlit
- [ ] Auto-improving loop usando `docs/eval-and-improve.md` no Claude Code

### Sprint 4
- [ ] Migrar para AWS ECS (se procurement Cogna aprovar)
- [ ] Integração com Microsoft Entra ID (SSO) — alinhado com CoE IA
- [ ] Métricas no Datadog
- [ ] Aprovação no Marketplace CoE IA com status "homologado"

### Backlog
- [ ] Multi-tenancy (vários bancos)
- [ ] Voice agent (Telegram/WhatsApp)
- [ ] Knowledge base de FAQs com pgvector
- [ ] Anti-fraude com signals comportamentais

---

## 20. Apêndices

### Apêndice A — Glossário

| Termo | Definição |
|-------|-----------|
| **AgentOS** | Runtime FastAPI da Agno que serve agentes em produção |
| **BYOC** | Bring Your Own Cloud — modelo no qual você hospeda o runtime |
| **Control Plane** | UI web `os.agno.com` para gerenciar AgentOS |
| **DeepInfra** | Provedor de inferência LLM open-weight com API OpenAI-compatible |
| **Team Coordinator** | Agente líder em `mode="coordinate"` que orquestra membros |
| **Tag oculta** | Marcação `[...]` na resposta do LLM, removida antes de exibir |
| **CoE IA** | Centro de Excelência em IA da Cogna |

### Apêndice B — Referências

| Documento | Localização |
|-----------|-------------|
| Desafio Técnico original | `Desafio_Te_cnico_Agentes_de_IA___1_.pdf` |
| Scaffold inicial | `README.md` do scaffold (gerado anteriormente) |
| Docs Agno | https://docs.agno.com |
| Agno docs MCP | https://docs.agno.com/mcp |
| DeepInfra integration Agno | https://docs.agno.com/models/providers/gateways/deepinfra/overview |
| Template Railway oficial | https://github.com/agno-agi/agentos-railway-template |
| Agno Skill | `npx skills add agno-agi/agno-skills --skill agno` |
| os.agno.com | https://os.agno.com |

### Apêndice C — Modelos DeepInfra de referência (jun/2026)

| Model ID | Family | Tool calling | Custo (in/out per M) | Uso |
|----------|--------|--------------|---------------------|-----|
| `Qwen/Qwen3-235B-A22B-Thinking-2507` | Qwen3 MoE | ✅ Forte | $0.30 / $1.20 | Coordinator, Entrevista |
| `deepseek-ai/DeepSeek-V3-0324` | DeepSeek V3 | ✅ Forte | $0.14 / $0.28 | Specialists |
| `meta-llama/Meta-Llama-3.3-70B-Instruct` | Llama 3.3 | ✅ Forte | $0.23 / $0.40 | Fallback estável |
| `Qwen/Qwen2.5-72B-Instruct` | Qwen2.5 | ✅ Bom | $0.23 / $0.40 | Alternativa Specialists |
| `mistralai/Mistral-Nemo-Instruct-2407` | Nemo | ⚠️ Variável | $0.13 / $0.13 | Não recomendado p/ tool calling complexo |

> **Atualizar conforme catálogo DeepInfra muda.** Antes da escolha final, validar `function_calling=true` em https://deepinfra.com/models?type=text-generation.

### Apêndice D — Comandos rápidos para Claude Code

```bash
# Setup inicial do projeto
claude code "Leia docs/SDD.md e execute TASK-001 a TASK-004"

# Implementar AgentOS app
claude code "Execute TASK-005 a TASK-008 do SDD"

# Refatorar UI Streamlit
claude code "Execute TASK-009 e TASK-010 do SDD"

# Criar suíte de testes
claude code "Execute TASK-013 e TASK-014 do SDD; rode os testes e ajuste até passar"

# Deploy
claude code "Execute TASK-015 a TASK-018 do SDD; documente outputs no docs/runbook.md"

# Auto-improve loop
claude code "Rode python -m evals, identifique falhas e edite os agentes para melhorar score"
```

### Apêndice E — Checklist de revisão pré-merge

- [ ] Todos os testes passam (`pytest tests/`)
- [ ] Evals com ≥ 90% pass rate (`python -m evals`)
- [ ] Lint sem erros (`ruff check`)
- [ ] Sem credenciais hardcoded (`git grep -i "di_\|sk-"`)
- [ ] `DEEPINFRA_API_KEY` apenas em env (`grep -r "DEEPINFRA_API_KEY" --include="*.py"`)
- [ ] README atualizado
- [ ] AGENTS.md presente
- [ ] Health check responde 200
- [ ] Tracing visível em os.agno.com
- [ ] Custo < $50/mês confirmado nas dashboards

---

**Fim do SDD.**

*Documento mantido em `docs/SDD.md`. Versionado junto ao código no repositório `banco-agil/`. Revisões: incrementar minor (`v1.1`, `v1.2`) para ajustes; major (`v2.0`) apenas para mudanças de arquitetura.*
