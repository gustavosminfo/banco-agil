# Runbook — Banco Ágil (Railway)

> Operação do AgentOS em produção, após `bash scripts/railway_up.sh`.

## Conectar o os.agno.com (modo Live)

1. Confirme que `JWT_VERIFICATION_KEY` está configurada no serviço Railway
   (`railway variables`). Se não estiver, rode `scripts/generate_jwt_keys.sh`
   e depois `railway variables set JWT_VERIFICATION_KEY="$(cat keys/jwt_public.pem)"`.
2. Pegue o domínio público: `railway domain`.
3. Em [os.agno.com](https://os.agno.com): **Add OS → Live** → cole o domínio
   → conecte. Requer plano Pro (coupon `PLATFORM30` dá 1 mês grátis — SDD §2.2).
4. Confirme que o chat e os traces aparecem na UI.

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
