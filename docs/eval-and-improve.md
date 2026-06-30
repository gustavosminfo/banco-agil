# Rodar evals e corrigir falhas

Você vai rodar a suite de evals, classificar cada falha por tipo, propor e aplicar correções
dentro do escopo, e re-rodar para confirmar que passaram — sem introduzir regressões.

## Passo 1 — Preparar o ambiente

```bash
# Ativar o virtualenv se ainda não estiver ativo
source .venv/bin/activate

# Garantir que o container local esteja rodando (os evals apontam para ele)
docker compose up -d
docker compose logs agent-os --tail 10
```

Confirme que o AgentOS subiu sem erros antes de continuar.

## Passo 2 — Rodar a suite completa

```bash
python -m evals -v
```

A flag `-v` exibe a resposta completa de cada caso. Anote o resultado de cada caso:
`nome_do_caso | PASS / FAIL | primeiro sinal do problema (1 frase)`

Se quiser rodar um caso isolado enquanto itera:
```bash
python -m evals --case <nome_do_caso>
```

## Passo 3 — Classificar cada falha

Para cada FAIL, classifique em uma das três categorias:

| Categoria | Sinal | Ação |
|---|---|---|
| **Regressão real** | O agente não cumpriu o critério que deveria cumprir | Editar o agente |
| **Critério ruim** | O critério é ambíguo, rígido demais, ou desatualizado | Editar `evals/cases.py` |
| **Juiz instável** | O veredicto muda entre execuções para a mesma resposta | Reformular o critério para ser mais binário |

Para distinguir regressão real de juiz instável, re-execute o caso suspeito 2–3 vezes:
```bash
python -m evals --case <nome> -v
```

Se o veredicto oscilar, é juiz instável → ajuste o critério em `evals/cases.py`.
Se for consistentemente FAIL, é regressão real → edite o agente.

## Passo 4 — Leia os arquivos relevantes antes de editar

Para cada falha classificada como **regressão real**:

1. Leia o arquivo do agente envolvido (`banco_agil/agents/<slug>.py` ou `banco_agil/team.py`).
2. Leia a ferramenta relevante em `banco_agil/tools/` se o problema for de tool calling.
3. Identifique a instrução ou condição que não está cobrindo o caso.

Para cada falha classificada como **critério ruim**:

1. Leia o caso em `evals/cases.py`.
2. Veja o que a resposta real do agente retornou (via `-v`).
3. Determine se o agente estava certo e o critério estava errado, ou vice-versa.

## Passo 5 — Aplicar correções

Aplique **uma correção de cada vez**, começando pelo caso mais grave (regressão real > critério
ruim > juiz instável).

**Editando um agente** (`banco_agil/agents/<slug>.py` ou `banco_agil/team.py`):
- Adicione ou reformule a instrução que cobre o caso
- Prefira tornar a regra mais específica e posicioná-la antes de regras gerais
- Não remova instruções existentes sem entender o que elas cobrem

**Editando um caso** (`evals/cases.py`):
- Torne o critério binário: "o agente FAZ X" em vez de "a resposta é boa"
- Evite critérios que dependem de valores que mudam (cotações, datas)
- Se o caso estiver cobrindo dois comportamentos, divida em dois casos separados

Após cada edição:
```bash
docker compose restart agent-os
python -m evals --case <nome_do_caso_corrigido>
```

## Passo 6 — Confirmar que todos passam

Após corrigir todos os casos:

```bash
python -m evals
```

Se algum caso novo falhar que antes passava — você introduziu regressão. Revise a última
edição e ajuste.

## Passo 7 — Persistir resultados no OS Agno (opcional)

Se `EVAL_DB_URL` estiver configurado no `.env` (URL pública do Postgres do Railway):

```bash
python -m evals --remote
```

Os resultados aparecerão na aba **Evaluation** do [os.agno.com](https://os.agno.com).

## Passo 8 — Commitar

```bash
git add evals/cases.py
git add banco_agil/agents/  # se algum agente foi editado
git add banco_agil/team.py  # se o Team foi editado

git commit -m "eval: corrige <n> caso(s) — <resumo das correções>"
git push
```

## Relatório final

```
Suite: <n> casos
Resultado antes: <n> PASS / <n> FAIL
Classificação das falhas:
  - Regressões reais: <n> (agentes editados: <lista>)
  - Critérios ruins: <n> (casos editados: <lista>)
  - Juiz instável: <n> (critérios reformulados: <lista>)
Resultado depois: <n> PASS / <n> FAIL
Commit: <hash>
```
