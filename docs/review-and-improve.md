# Revisão e varredura periódica do repositório

Você vai verificar a coerência mecânica do repositório: agentes no disco registrados corretamente,
variáveis de ambiente documentadas, imports consistentes, runbook atualizado. Corrija o que puder
automaticamente e apresente uma punch list do resto.

Execute esta varredura antes de releases públicas e periodicamente durante desenvolvimento ativo.

## Verificação 1 — Consistência dos agentes registrados

**Agentes no disco:**
```bash
ls banco_agil/agents/*.py
```
(exclua `__init__.py`)

Para cada arquivo de agente encontrado:

1. Confirme que o agente está exportado em `banco_agil/agents/__init__.py`:
   - Deve ter `from banco_agil.agents.<slug> import <slug>_agent`
   - Deve estar na lista `__all__`

2. Confirme que o agente está importado em `app/main.py`:
   - Deve aparecer na linha `from banco_agil.agents import ...`
   - Deve estar na lista `agents=[...]` do `Registry`

3. Se o agente é um membro do Team: confirme que está na lista `members=[...]` em
   `banco_agil/team.py`.

**Correção automática:** adicione os imports e registros ausentes nos arquivos acima.

## Verificação 2 — Variáveis de ambiente documentadas

Leia `.env` e `example.env`. Para cada variável em `.env`:

1. Confirme que existe uma linha correspondente em `example.env` (sem o valor real, só o nome
   e um comentário explicativo).
2. Variáveis que não devem ser commitadas (chaves de API, tokens JWT, URLs de banco) devem
   estar em `.gitignore` via `.env` ou `.env.production` — confirme.

**Correção automática:** adicione em `example.env` qualquer variável documentada em `.env` que
esteja faltando. Não copie valores reais — apenas o nome e um comentário descritivo.

## Verificação 3 — Imports sem uso e dependências quebradas

Para cada arquivo em `banco_agil/`:

1. Leia os imports e confirme que cada um é realmente usado no arquivo.
2. Para imports de ferramentas nos agentes: confirme que a ferramenta existe em
   `banco_agil/tools/`.
3. Para imports em `app/main.py`: confirme que todos os módulos importados existem.

**Correção automática:** remova imports sem uso. Se um import aponta para um arquivo que não
existe, adicione na punch list — pode indicar um arquivo deletado ou renomeado.

## Verificação 4 — Runbook desatualizado

Leia `docs/runbook.md`. Verifique:

1. **Sintomas documentados** — algum bug listado foi corrigido desde a última atualização?
   Se sim, marque como "resolvido" ou remova a seção.
2. **Funcionalidades do painel** — a tabela de status (Chat, Traces, Studio, etc.) ainda
   reflete a realidade? Compare com o que está configurado em `app/main.py`.
3. **Nomes de serviços Railway** — o nome do serviço nos comandos `railway logs --service X`
   ainda bate com o `railway.json`?

**Correção automática:** atualize seções desatualizadas que você consegue verificar pelo código.
Adicione na punch list as seções que exigem validação manual (ex.: estado de serviços externos).

## Verificação 5 — Cobertura de evals

Leia `evals/cases.py`. Para cada agente registrado (`triagem`, `credito`, `entrevista`,
`cambio`):

1. Existe ao menos 1 caso de golden path?
2. Existe ao menos 1 caso de edge case ou adversarial?

Se um agente não tem nenhuma cobertura, adicione na punch list:
`"EVAL AUSENTE: adicionar casos para <slug>"`.

Não crie casos de eval automaticamente — isso requer entendimento do comportamento esperado
que deve ser validado com o usuário.

## Verificação 6 — `railway.json` e `Dockerfile` alinhados

1. O `CMD` no `Dockerfile` aponta para `app.main:app`?
2. O `startCommand` em `railway.json` é consistente com o `Dockerfile`?
3. O número de réplicas (`numReplicas`) em `railway.json` é intencional?

**Correção automática:** apenas inconsistências claras (ex.: o `Dockerfile` referencia um
arquivo que não existe). Mudanças de réplicas ou recursos sempre vão para a punch list.

## Saída: punch list

Ao final da varredura, imprima dois blocos:

```
## Corrigido automaticamente
- [ ] <descrição do que foi corrigido> — arquivo: <path>
...

## Punch list (requer ação manual)
- [ ] <descrição do problema> — arquivo: <path>
...
```

Se não houver nada na punch list, escreva: `Repositório coerente — nenhuma ação manual necessária.`

## Commitar as correções automáticas

Se houve correções automáticas:

```bash
git add <arquivos editados>
git commit -m "chore: varredura periódica — <resumo das correções>"
git push
```
