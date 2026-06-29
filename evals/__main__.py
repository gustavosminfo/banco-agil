"""
evals/__main__.py
Runner de evals do Banco Ágil — executa cada caso de evals/cases.py e julga
a transcrição completa com AgentAsJudgeEval.

Dois modos:
  - Local: constrói o Team em processo e chama team.arun() diretamente
    (requer DEEPINFRA_API_KEY e Postgres acessível via DB_URL).
  - Remoto (--remote): chama o AgentOS real via HTTP (AGENTOS_URL), exatamente
    como a UI Streamlit faz — útil para validar contra produção, sem precisar
    de um Postgres local.

Os casos rodam SEQUENCIALMENTE (nunca em paralelo): o Team é um único objeto
em memória por processo do AgentOS, e rodar sessões diferentes ao mesmo tempo
pode contaminar o session_state de uma sessão nova com o estado de outra
ainda em andamento (confirmado experimentalmente: uma sessão nova "nasceu"
bloqueada por tentativas de autenticação de OUTRO caso rodando em paralelo).

Uso:
    python -m evals                          # todos os casos, local
    python -m evals --case auth_happy_path    # um caso isolado, local
    python -m evals --remote                  # todos os casos, contra AGENTOS_URL
"""

import argparse
import asyncio
import os
import sys
import uuid

if sys.platform == "win32":
    # psycopg em modo assíncrono não funciona com o ProactorEventLoop, que é
    # o padrão do asyncio no Windows. Em produção (Railway/Linux) isso não
    # se aplica — esse ajuste é só para rodar `python -m evals` localmente.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
    # O console do Windows usa cp1252 por padrão, que não representa emojis
    # presentes nas respostas reais dos agentes — força UTF-8 na saída.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

import httpx
from agno.db.postgres import PostgresDb
from agno.eval.agent_as_judge import AgentAsJudgeEval

from banco_agil.config import EVAL_DB_URL, get_specialist_model
from banco_agil.team import criar_equipe, limpar_tags_da_resposta
from evals.cases import CASES, EvalCase

PASS_RATE_THRESHOLD = 90.0  # % mínimo de casos aprovados (SDD §16.2)

# Se configurado, persiste os resultados no mesmo Postgres do AgentOS de
# produção — populando a aba Evaluation do os.agno.com. Opcional: sem
# EVAL_DB_URL, os evals funcionam normalmente, só sem essa persistência.
_EVAL_DB = PostgresDb(db_url=EVAL_DB_URL) if EVAL_DB_URL else None


async def _rodar_conversa_local(team, prompts: list[str]) -> list[str]:
    """Executa os prompts em sequência numa sessão nova via Team em processo.
    Retorna a lista de respostas do atendente (uma por prompt)."""
    session_id = str(uuid.uuid4())
    respostas: list[str] = []

    for prompt in prompts:
        run = await team.arun(prompt, session_id=session_id)
        respostas.append(str(run.content) if run.content else "")

    return respostas


async def _rodar_conversa_remota(client: httpx.AsyncClient, prompts: list[str]) -> list[str]:
    """Executa os prompts em sequência numa sessão nova via AgentOS real (HTTP).
    Retorna a lista de respostas do atendente (uma por prompt)."""
    session_id = str(uuid.uuid4())
    respostas: list[str] = []

    for prompt in prompts:
        resp = await client.post(
            "/teams/banco-agil/runs",
            data={"message": prompt, "session_id": session_id, "stream": "false"},
        )
        resp.raise_for_status()
        respostas.append(str(resp.json().get("content") or ""))

    return respostas


async def _rodar_caso(caso: EvalCase, team=None, client: httpx.AsyncClient | None = None) -> bool:
    print(f"\n=== Caso: {caso.name} ===")
    if client is not None:
        respostas = await _rodar_conversa_remota(client, caso.prompts)
    else:
        respostas = await _rodar_conversa_local(team, caso.prompts)

    respostas_limpas = [limpar_tags_da_resposta(r) for r in respostas]

    # Transcrição com rótulos — só para leitura/debug humano.
    transcricao_debug = "\n".join(
        f"Cliente: {p}\nAtendente: {r}" for p, r in zip(caso.prompts, respostas_limpas)
    )
    print(f"--- Transcrição: {caso.name} ---\n{transcricao_debug}\n-------------------")

    # Para o juiz: só as respostas do atendente, sem rótulos artificiais do
    # nosso script (que o juiz tende a confundir com "metadado exposto").
    saida_para_juiz = "\n\n".join(respostas_limpas)

    # O modelo-juiz (specialist) ocasionalmente retorna um JSON malformado
    # para o schema esperado (lista em vez de objeto) — tenta de novo antes
    # de desistir, em vez de derrubar a suíte inteira por um caso só.
    resultado = None
    for tentativa in range(2):
        judge = AgentAsJudgeEval(
            name=caso.name,
            criteria=caso.criteria,
            scoring_strategy="binary",
            model=get_specialist_model(),
            db=_EVAL_DB,
        )
        try:
            resultado = await judge.arun(input="\n".join(caso.prompts), output=saida_para_juiz)
            break
        except Exception as exc:
            print(f"[AVISO] Juiz falhou na tentativa {tentativa + 1} para {caso.name}: {exc}")

    passou = bool(resultado and resultado.pass_rate >= 100.0)
    motivo = resultado.results[0].reason if resultado and resultado.results else "(sem motivo)"
    print(f"[{'PASSOU' if passou else 'FALHOU'}] {caso.name} — {motivo}")
    return passou


async def _rodar_caso_seguro(caso: EvalCase, **kwargs) -> bool:
    """Garante que uma falha inesperada num caso não derrube a suíte inteira."""
    try:
        return await _rodar_caso(caso, **kwargs)
    except Exception as exc:
        print(f"[ERRO] Caso {caso.name} falhou com exceção: {exc}")
        return False


async def _main_async(casos: list[EvalCase], remote: bool) -> float:
    resultados = []

    if remote:
        agentos_url = os.getenv("AGENTOS_URL", "http://localhost:8000")
        agentos_api_key = os.getenv("AGENTOS_API_KEY", "")
        headers = {"Authorization": f"Bearer {agentos_api_key}"} if agentos_api_key else {}
        # 280s: pouco abaixo do limite de gateway do Railway (300s) — alguns
        # turnos com modelos "Thinking" já levaram mais de 200s em produção.
        async with httpx.AsyncClient(base_url=agentos_url, headers=headers, timeout=280.0) as client:
            for caso in casos:
                resultados.append(await _rodar_caso_seguro(caso, client=client))
    else:
        team = criar_equipe()
        for caso in casos:
            resultados.append(await _rodar_caso(caso, team=team))

    total = len(resultados)
    aprovados = sum(1 for ok in resultados if ok)
    taxa = (aprovados / total * 100) if total else 0.0

    print(f"\n=== Resumo: {aprovados}/{total} casos aprovados ({taxa:.1f}%) ===")
    for caso, ok in zip(casos, resultados):
        print(f"  {'✅' if ok else '❌'} {caso.name}")
    return taxa


def main() -> None:
    parser = argparse.ArgumentParser(description="Evals do Banco Ágil")
    parser.add_argument("--case", help="Nome de um caso específico (ver evals/cases.py)")
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Roda contra o AgentOS real (AGENTOS_URL) em vez de um Team local",
    )
    args = parser.parse_args()

    print(
        "Persistência de evals: "
        + ("ATIVA (EVAL_DB_URL configurada)" if _EVAL_DB else "desligada (defina EVAL_DB_URL para ativar)")
    )

    casos = CASES
    if args.case:
        casos = [c for c in CASES if c.name == args.case]
        if not casos:
            print(f"Caso '{args.case}' não encontrado. Casos disponíveis:")
            for c in CASES:
                print(f"  - {c.name}")
            sys.exit(1)

    taxa = asyncio.run(_main_async(casos, remote=args.remote))

    if taxa < PASS_RATE_THRESHOLD:
        sys.exit(1)


if __name__ == "__main__":
    main()
