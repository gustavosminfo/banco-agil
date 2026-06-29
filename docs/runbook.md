# Runbook — Banco Ágil (Railway)

> Operação do AgentOS em produção, após `bash scripts/railway_up.sh`.

## Conectar o os.agno.com (modo Live)

**Status: conectado.** `JWT_VERIFICATION_KEY` já está configurada no
serviço Railway (par de chaves em `keys/`, gitignored) e o domínio
`banco-agil-production.up.railway.app` está adicionado em modo Live no
painel do os.agno.com, usando o cupom `PLATFORM30` (1 mês grátis — SDD
§2.2) em vez de assinar o plano Pro diretamente. Validado enviando uma
chamada de teste a `/teams/banco-agil/runs` e confirmando que o chat e os
traces apareceram no painel.

**Para reconectar (ex.: novo domínio, chave rotacionada, cupom expirou):**

1. Confirme que `JWT_VERIFICATION_KEY` está configurada no serviço Railway
   (`railway variables`). Se não estiver, rode `scripts/generate_jwt_keys.sh`
   e depois `railway variables set JWT_VERIFICATION_KEY="$(cat keys/jwt_public.pem)"`.
2. Pegue o domínio público: `railway domain`.
3. Em [os.agno.com](https://os.agno.com): **Add OS → Live** → cole o domínio
   → conecte. Conectar uma instância remota exige plano Pro — aplique o
   cupom `PLATFORM30` na tela de assinatura se ainda for válido; senão,
   é necessário assinar (decisão financeira do usuário, não automatizável).
4. Confirme que o chat e os traces aparecem na UI.

### Funcionalidades do painel: o que está habilitado e por quê

| Aba | Status | Motivo |
|---|---|---|
| Chat, Traces | ✅ Habilitado | Funciona desde a conexão inicial (item acima). |
| Approvals, Scheduler, Studio | ✅ Habilitado | `app/main.py` passa `db=PostgresDb(...)` ao `AgentOS(...)` (antes só o `Team` tinha banco próprio). Síncrono — exigido especificamente pelo Studio (Components), que rejeita um `AsyncBaseDb`. |
| Metrics | ✅ Habilitado | Além do `db=` acima, é uma agregação que precisa ser disparada manualmente: `POST /metrics/refresh`. Sem isso, fica vazio (`updated_at: null`) mesmo com sessões reais registradas. |
| Evaluation | ✅ Habilitado | Nossos evals (`evals/cases.py`) rodavam via `AgentAsJudgeEval` direto em Python, sem nunca escrever no banco do AgentOS. `evals/__main__.py` agora passa `db=PostgresDb(db_url=EVAL_DB_URL)` ao `AgentAsJudgeEval` quando `EVAL_DB_URL` está configurada (`.env`) — usa a `DATABASE_PUBLIC_URL` do plugin Postgres da Railway para escrever no mesmo banco que o AgentOS lê. |
| Memory | ✅ Habilitado | `Team(update_memory_on_run=True)` em `banco_agil/team.py`, escopado por `user_id` (o CPF do cliente, repassado por `ui/streamlit_app.py` depois da autenticação via `[AUTH_OK]`). Escolhido em vez de `enable_agentic_memory` para evitar o "agentic memory token trap" documentado pelo Agno (custo pode multiplicar 8x conforme memórias acumulam). |
| Knowledge | ❌ Indisponível | Exige uma instância de `Knowledge` (base vetorial via pgvector + embedder) — desenvolvimento novo, não apenas configuração. Não é requisito do desafio técnico (sem RAG no escopo atual). |
| Learning | ❌ Indisponível | Exige `LearningMachine` configurado nos agentes — mesma situação do Knowledge, fora do escopo do desafio. |

**Para popular Metrics manualmente:** `curl -X POST <url>/metrics/refresh`.

### Studio: registrado para experimentação, não para produção

`app/main.py` registra os 4 agentes e o `Team` num `Registry`, passado ao
`AgentOS(registry=...)`. Isso os torna **reutilizáveis como peça** ao
montar Teams/Workflows novos visualmente no Studio (ex.: testar um
workflow experimental com `Condition`/`Router` para o fluxo de crédito).

**Decisão deliberada**: não editamos nem publicamos a lógica de
produção *através* do Studio. As versões do Studio ficam salvas no
Postgres, não no Git — editar o Team por lá criaria uma segunda fonte de
verdade divergente do código, e nosso deploy (`criar_equipe()` em
`app/main.py`) nunca lê versões publicadas no Studio, então editar por
lá não mudaria o comportamento em produção sem reescrever o
`app/main.py` para isso. Mantemos a lógica bancária 100% versionada no
Git, com histórico de commits revisável — importante numa aplicação
bancária. Use o Studio só para prototipar ideias novas, isoladamente.

**Por que síncrono e não assíncrono?** Tínhamos trocado `PostgresDb` por
`AsyncPostgresDb` por achar (incorretamente, na época) que isso resolvia
um travamento de startup em produção. O próprio commit dessa troca já
registrava que o travamento persistia mesmo depois — a causa real era
um volume do Postgres mal anexado na Railway, já corrigido. A
documentação oficial do Agno recomenda explicitamente `PostgresDb`
síncrono como "o banco de produção" e o usa diretamente nos próprios
exemplos de AgentOS/FastAPI — voltamos para alinhar com isso, o que
também desbloqueou o Studio de graça (ver README, "Desafios enfrentados",
item 3).

## Rotacionar a DEEPINFRA_API_KEY

```bash
railway variables set DEEPINFRA_API_KEY="<nova-key>"
railway up   # força redeploy para a env var entrar em efeito
```

Gere a nova key no painel da DeepInfra **antes** de revogar a antiga, para
não haver janela sem chave válida.

## Restaurar backup do Postgres

O Postgres do Railway tem backups automáticos diários (plano Hobby+).

```bash
railway connect postgres        # abre psql apontando para o serviço
# dentro do painel Railway: Postgres service → Data → Backups → Restore
```

Não há comando de restore via CLI — é feito pela UI do Railway, escolhendo
o snapshot e confirmando o restore (substitui o banco atual).

## Rollback de deploy

```bash
railway deployments            # lista deploys anteriores com seus IDs
railway redeploy <deployment-id>
```

Alternativamente, pela UI do Railway: **Deployments → (deploy anterior) →
Redeploy**.

## Checklist rápido de incidente

- [ ] `curl https://<domínio>/health` → 200?
- [ ] `railway logs` → algum erro recente (timeout DeepInfra, Postgres, etc.)?
- [ ] `railway variables` → todas as obrigatórias presentes (`DEEPINFRA_API_KEY`,
      `DB_URL`, `AGNO_TELEMETRY`)?
- [ ] Dashboard DeepInfra → key ainda válida e dentro do limite de uso?

## Sintoma: sessão nova "nasce" bloqueada (contaminação de session_state)

Se uma conversa **nova** (CPF válido, primeira mensagem) já responder com
"Por segurança, o acesso foi bloqueado após 3 tentativas" — isso é o bug
conhecido descrito no README (seção "Desafios enfrentados", item 7): o
estado em memória do processo do AgentOS parece acumular tentativas de
falha entre sessões diferentes ao longo de uma execução longa do
processo. Não há correção definitiva aplicada ainda.

**Contorno:** reiniciar o serviço do AgentOS limpa o estado em memória:

```bash
railway redeploy <deployment-id-atual>   # ou: Deployments → Restart, pela UI
```

Confirme a limpeza testando uma sessão nova logo após o restart (CPF
válido deve autenticar normalmente, sem menção a bloqueio).
