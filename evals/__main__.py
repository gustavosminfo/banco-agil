"""
evals/__main__.py
Runner de evals do Banco Ágil — executa cada caso de evals/cases.py contra
o Team real (requer DEEPINFRA_API_KEY válida e Postgres acessível, conforme
DB_URL) e julga a transcrição completa com AgentAsJudgeEval.

Uso:
    python -m evals                       # roda todos os casos
    python -m evals --case auth_happy_path # roda um caso isolado
"""

import argparse
import asyncio
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

from agno.eval.agent_as_judge import AgentAsJudgeEval

from banco_agil.config import get_specialist_model
from banco_agil.team import criar_equipe, limpar_tags_da_resposta
from evals.cases import CASES, EvalCase

PASS_RATE_THRESHOLD = 90.0  # % mínimo de casos aprovados (SDD §16.2)


async def _rodar_conversa(team, prompts: list[str]) -> tuple[str, str]:
    """Executa os prompts em sequência numa sessão nova e retorna
    (transcrição completa, última resposta limpa)."""
    session_id = str(uuid.uuid4())
    transcricao: list[str] = []
    ultima_resposta = ""

    for prompt in prompts:
        transcricao.append(f"Cliente: {prompt}")
        # O Team usa AsyncPostgresDb — run() síncrono não é suportado.
        run = await team.arun(prompt, session_id=session_id)
        resposta = str(run.content) if run.content else ""
        ultima_resposta = limpar_tags_da_resposta(resposta)
        transcricao.append(f"Atendente: {resposta}")

    return "\n".join(transcricao), ultima_resposta


async def _rodar_caso(team, caso: EvalCase) -> bool:
    print(f"\n=== Caso: {caso.name} ===")
    transcricao, _ = await _rodar_conversa(team, caso.prompts)
    print(f"--- Transcrição ---\n{transcricao}\n-------------------")

    judge = AgentAsJudgeEval(
        name=caso.name,
        criteria=caso.criteria,
        scoring_strategy="binary",
        model=get_specialist_model(),
        print_summary=True,
        print_results=True,
    )
    resultado = await judge.arun(input="\n".join(caso.prompts), output=transcricao)

    passou = bool(resultado and resultado.pass_rate >= 100.0)
    print(f"[{'PASSOU' if passou else 'FALHOU'}] {caso.name}")
    return passou


async def _main_async(casos: list[EvalCase]) -> float:
    team = criar_equipe()

    resultados = []
    for caso in casos:
        resultados.append((caso.name, await _rodar_caso(team, caso)))

    total = len(resultados)
    aprovados = sum(1 for _, ok in resultados if ok)
    taxa = (aprovados / total * 100) if total else 0.0

    print(f"\n=== Resumo: {aprovados}/{total} casos aprovados ({taxa:.1f}%) ===")
    return taxa


def main() -> None:
    parser = argparse.ArgumentParser(description="Evals do Banco Ágil")
    parser.add_argument("--case", help="Nome de um caso específico (ver evals/cases.py)")
    args = parser.parse_args()

    casos = CASES
    if args.case:
        casos = [c for c in CASES if c.name == args.case]
        if not casos:
            print(f"Caso '{args.case}' não encontrado. Casos disponíveis:")
            for c in CASES:
                print(f"  - {c.name}")
            sys.exit(1)

    taxa = asyncio.run(_main_async(casos))

    if taxa < PASS_RATE_THRESHOLD:
        sys.exit(1)


if __name__ == "__main__":
    main()
