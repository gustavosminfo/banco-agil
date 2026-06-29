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
| Approvals, Scheduler, Metrics, Evaluation, Studio | ✅ Habilitado | `app/main.py` passa `db=PostgresDb(...)` ao `AgentOS(...)` (antes só o `Team` tinha banco próprio). Síncrono — exigido especificamente pelo Studio (Components), que rejeita um `AsyncBaseDb`. Ao acessar via API diretamente (não pela UI), pode ser necessário passar `?db_id=...` — há 2 bancos registrados agora (Team + AgentOS). Ver nota abaixo sobre por que voltamos ao síncrono. |
| Knowledge | ❌ Indisponível | Exige uma instância de `Knowledge` (base vetorial via pgvector + embedder) — desenvolvimento novo, não apenas configuração. Não é requisito do desafio técnico (sem RAG no escopo atual). |
| Learning | ❌ Indisponível | Exige `LearningMachine` configurado nos agentes — mesma situação do Knowledge, fora do escopo do desafio. |

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
