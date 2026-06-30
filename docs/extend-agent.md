# Estender um agente com uma mudança específica

Você vai aplicar uma mudança pontual descrita pelo usuário — nova ferramenta, refinamento de
prompt, correção de bug — de forma incremental e verificada. Uma mudança por iteração.

## Passo 1 — Entender a mudança

Pergunte ao usuário:

1. **Qual agente** (ou arquivo) deve ser alterado?
2. **O que exatamente** deve mudar? (tool a adicionar, regra a refinar, bug a corrigir)
3. **Como você saberia que a mudança funcionou?** — peça um exemplo de prompt e o comportamento
   esperado após a mudança.

Se a mudança envolver uma nova ferramenta, pergunte:
- Nome da função, parâmetros e tipos
- O que ela retorna (tipo e formato)
- Fonte dos dados (CSV local, API externa, cálculo interno?)

Não prossiga sem ter uma definição clara e um critério de sucesso.

## Passo 2 — Pesquisar antes de criar

Antes de escrever código novo:

1. Leia `banco_agil/tools/` — a ferramenta que você precisa pode já existir ou ser uma
   pequena extensão de uma existente.
2. Leia o arquivo do agente-alvo — entenda o contexto das instruções existentes antes de
   adicionar novas.
3. Se a mudança envolve uma API externa nova, consulte a documentação Agno via MCP
   (`agno-docs`) para ver se existe um `Toolkit` pronto.

## Passo 3 — Aplicar a mudança (uma de cada vez)

### Adicionar uma ferramenta nova

1. Crie (ou edite) o arquivo em `banco_agil/tools/<domínio>_tools.py`.
2. Escreva a função com tipagem completa e uma docstring de uma linha.
3. Importe-a no arquivo do agente: `from banco_agil.tools.<domínio>_tools import <função>`.
4. Adicione à lista `tools=[...]` do agente.
5. Adicione uma instrução descrevendo **quando** usar a ferramenta (condição + ação).

### Refinar um prompt

1. Localize a instrução específica a mudar nas `instructions=[...]` do agente.
2. Edite **apenas essa instrução** — não reescreva o bloco inteiro.
3. Se estiver adicionando uma nova regra, posicione-a na seção semântica correta
   (Identidade, Fluxo, Segurança, Escopo etc.) usando o padrão `# ── N. Seção ──`.

### Corrigir um bug

1. Leia `docs/runbook.md` — bugs conhecidos estão documentados lá.
2. Identifique a causa raiz (instrução ambígua? ferramenta ausente? condição não coberta?).
3. Aplique a correção mínima que resolve a causa raiz sem alterar o comportamento de outros
   fluxos.

## Passo 4 — Testar a mudança

```bash
docker compose restart agent-os
docker compose logs agent-os --tail 10
```

Envie o exemplo de prompt definido no Passo 1:

```bash
curl -s -X POST http://localhost:8000/teams/banco-agil/runs \
  -H "Content-Type: application/json" \
  -d '{
    "message": "<prompt do critério de sucesso>",
    "session_id": "extend-test-1",
    "stream": false
  }' | python -m json.tool
```

Verifique:
- A resposta satisfaz o critério de sucesso?
- Os logs mostram a ferramenta correta sendo chamada (se a mudança envolvia uma ferramenta)?
- Nenhuma tag interna apareceu na resposta?

Se falhar, volte ao Passo 3 com um ajuste diferente. Não empilhe múltiplas mudanças de uma vez.

## Passo 5 — Verificar regressões

```bash
source .venv/bin/activate
python -m evals
```

Se algum eval existente falhar, a mudança introduziu regressão. Ajuste-a para preservar o
comportamento existente antes de prosseguir.

## Passo 6 — Commitar

```bash
git add <arquivos alterados>
git commit -m "extend(<slug>): <resumo de 1 linha>"
git push
```

Exemplos de mensagens:
- `extend(cambio): adiciona suporte a cotação de iene`
- `extend(credito): refina regra de score mínimo para parcelamento`
- `extend(triagem): corrige falso positivo de bloqueio em sessão nova`

## Passo 7 — Relatório

```
Agente: <nome>
Mudança aplicada: <descrição>
Arquivos alterados: <lista>
Teste de critério: PASS / FAIL
Evals de regressão: PASS / FAIL
Commit: <hash>
```

Se o usuário quiser continuar com outra mudança, volte ao Passo 1.
