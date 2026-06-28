# 🏦 Banco Ágil — Agente Bancário Inteligente

Sistema de atendimento ao cliente por múltiplos agentes de IA especializados,
desenvolvido com **Agno** + **Claude Sonnet 4.6** + **Streamlit**.

---

## Visão Geral

O Banco Ágil simula o atendimento de um banco digital por meio de quatro agentes
de IA que operam de forma coordenada e **imperceptível ao cliente**: para o usuário,
existe um único atendente com habilidades diferentes.

```
Cliente ──► Team Coordinator (Agno mode="coordinate")
                 ├── Agente de Triagem      (autenticação + roteamento)
                 ├── Agente de Crédito      (consulta e aumento de limite)
                 ├── Agente de Entrevista   (recálculo de score)
                 └── Agente de Câmbio       (cotações em tempo real)
```

---

## Arquitetura

### Camada de agentes (`banco_agil/agents/`)

| Agente | Responsabilidade | Ferramentas |
|--------|-----------------|-------------|
| Triagem | Auth CPF + data de nascimento; identificar assunto | `autenticar_cliente`, `buscar_dados_cliente` |
| Crédito | Consultar limite; processar aumento; checar score | `consultar_limite_credito`, `solicitar_aumento_limite`, `verificar_limite_pelo_score` |
| Entrevista | Coletar dados financeiros; calcular score; atualizar CSV | `calcular_score_credito`, `atualizar_score_cliente` |
| Câmbio | Cotação em tempo real via AwesomeAPI | `consultar_cotacao`, `listar_moedas_suportadas` |

### Camada de ferramentas (`banco_agil/tools/`)

Funções Python puras que operam sobre os arquivos CSV e APIs externas:

- **auth_tools.py** — leitura de `clientes.csv`, normalização de CPF e data
- **credit_tools.py** — consulta de `clientes.csv` e `score_limite.csv`; escrita em `solicitacoes_aumento_limite.csv`
- **interview_tools.py** — cálculo de score pela fórmula ponderada; update em `clientes.csv`
- **exchange_tools.py** — chamada HTTP à [AwesomeAPI](https://economia.awesomeapi.com.br) (gratuita, sem chave)

### Coordenação (`banco_agil/team.py`)

- `mode="coordinate"` — o Team Leader mantém contexto e decide qual agente acionar.
- `session_state` — persiste autenticação, CPF, score e agente ativo entre turnos.
- `SqliteStorage` — sessão sobrevive a recarregamentos do Streamlit (`tmp/banco_agil.db`).
- Tags ocultas (`[AUTH_OK|...]`, `[ROUTE|...]`) são usadas para comunicação entre o agente e o coordenador sem vazar para o cliente.

### Fórmula de score (Entrevista)

```
score = (renda / (despesas + 1)) * 30
        + peso_emprego[tipo]          # formal=300, autônomo=200, desempregado=0
        + peso_dependentes[n]         # 0=100, 1=80, 2=60, 3+=30
        + peso_dividas[tem_dividas]   # não=+100, sim=-100
```

Score limitado a [0, 1000].

### Tabela score × limite (`data/score_limite.csv`)

| Score | Limite máximo |
|-------|--------------|
| 0–399 | R$ 1.000 |
| 400–499 | R$ 2.000 |
| 500–599 | R$ 4.000 |
| 600–699 | R$ 6.000 |
| 700–799 | R$ 10.000 |
| 800–1000 | R$ 20.000 |

---

## Funcionalidades implementadas

- [x] Autenticação com CPF + data de nascimento (até 3 tentativas)
- [x] Bloqueio após 3 falhas consecutivas
- [x] Consulta de limite de crédito
- [x] Solicitação de aumento de limite com aprovação/rejeição automática
- [x] Redirecionamento para entrevista em caso de rejeição
- [x] Entrevista financeira conversacional (uma pergunta por vez)
- [x] Recálculo de score e atualização em `clientes.csv`
- [x] Redirecionamento de volta ao Agente de Crédito após entrevista
- [x] Cotação de câmbio em tempo real (USD, EUR, GBP, BTC, JPY)
- [x] Encerramento gracioso a qualquer momento
- [x] Histórico de solicitações em `solicitacoes_aumento_limite.csv`
- [x] Sessão persistente entre recarregamentos (SQLite)
- [x] Interface Streamlit com sidebar de ajuda

---

## Estrutura de diretórios

```
banco-agil/
├── banco_agil/
│   ├── __init__.py
│   ├── config.py             # Paths, constantes, model ID
│   ├── team.py               # BancoAgilTeam (Agno Team)
│   ├── agents/
│   │   ├── triagem.py
│   │   ├── credito.py
│   │   ├── entrevista.py
│   │   └── cambio.py
│   └── tools/
│       ├── auth_tools.py
│       ├── credit_tools.py
│       ├── interview_tools.py
│       └── exchange_tools.py
├── data/
│   ├── clientes.csv                       # Base de clientes
│   ├── score_limite.csv                   # Tabela score × limite
│   └── solicitacoes_aumento_limite.csv    # Criado em runtime
├── tmp/
│   └── banco_agil.db                      # Criado em runtime (SQLite)
├── app.py                                 # UI Streamlit
├── requirements.txt
├── .env.example
└── README.md
```

---

## Tutorial de execução

### Pré-requisitos

- Python 3.11+
- Conta Anthropic com API key ([console.anthropic.com](https://console.anthropic.com))

### 1. Instalar dependências

```bash
cd banco-agil
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite .env e insira sua ANTHROPIC_API_KEY
```

### 3. Executar a aplicação

```bash
streamlit run app.py
```

Acesse em: `http://localhost:8501`

### 4. Testar com Claude Code / Codex

```bash
# Instalar o Skill oficial do Agno no Claude Code
npx skills add agno-agi/agno-skills --skill agno

# Depois, no Claude Code:
# "Explique a arquitetura do time em banco_agil/team.py"
# "Adicione suporte a PIX no Agente de Crédito"
```

---

## Escolhas técnicas

| Decisão | Justificativa |
|---------|--------------|
| **Agno** | Sessão stateful nativa, Team com mode="coordinate", MCP de primeira classe, instantiation de microsegundos |
| **mode="coordinate"** | Permite ao coordenador manter contexto cross-turn e encadear agentes (Entrevista → Crédito) sem reautenticação |
| **Tags ocultas** | Padrão leve para comunicação agente↔coordenador sem depender de structured output do LLM |
| **AwesomeAPI** | Gratuita, sem chave, cobertura completa de moedas em BRL |
| **SQLite** | Zero-config, arquivo local, suficiente para demo e testes |
| **Streamlit** | Requisito do desafio; integra naturalmente com Python puro |

---

## Desafios e soluções

### Transição imperceptível entre agentes
**Problema:** O cliente não pode perceber a troca de agentes.  
**Solução:** `mode="coordinate"` no Team — o coordenador age como único interlocutor e oculta os handoffs. As tags (`[ROUTE|...]`) são removidas da resposta final.

### Estado de autenticação entre turnos
**Problema:** Precisamos saber em cada turno se o cliente já autenticou.  
**Solução:** Dois níveis de estado — `session_state` do Agno Team (persistido em SQLite) + `st.session_state` do Streamlit para feedback imediato na UI.

### Retry de autenticação com limite
**Problema:** Máximo 3 tentativas, após o que o atendimento encerra.  
**Solução:** `tentativas_auth` no contexto injetado em cada mensagem; o coordenador verifica e encerra se `>= MAX_AUTH_ATTEMPTS`.

### Retorno ao Agente de Crédito após Entrevista
**Problema:** Após recalcular o score, o cliente deve poder tentar o aumento novamente sem reautenticar.  
**Solução:** Tag `[ROUTE|credito|score_atualizado=X]` que atualiza o score no estado e redireciona ao Agente de Crédito com o novo contexto.

---

## Extensões sugeridas

- [ ] Substituir SQLite por PostgreSQL para deploy multi-usuário
- [ ] Adicionar AgentOS para monitoramento em produção
- [ ] Implementar MCP server para integração com sistemas bancários reais
- [ ] Adicionar autenticação por biometria (foto via multimodal Claude)
- [ ] Dashboard de solicitações em tempo real (usando `solicitacoes_aumento_limite.csv`)
