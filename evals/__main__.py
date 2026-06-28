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
import sys
import uuid

from agno.eval.agent_as_judge import AgentAsJudgeEval

from banco_agil.config import get_specialist_model
from banco_agil.team import criar_equipe, limpar_tags_da_resposta
from evals.cases import CASES, EvalCase

PASS_RATE_THRESHOLD = 90.0  # % mínimo de casos aprovados (SDD §16.2)


def _rodar_conversa(team, prompts: list[str]) -> tuple[str, str]:
    """Executa os prompts em sequência numa sessão nova e retorna
    (transcrição completa, última resposta limpa)."""
    session_id = str(uuid.uuid4())
    transcricao: list[str] = []
    ultima_resposta = ""

    for prompt in prompts:
        transcricao.append(f"Cliente: {prompt}")
        run = team.run(prompt, session_id=session_id)
        resposta = str(run.content) if run.content else ""
        ultima_resposta = limpar_tags_da_resposta(resposta)
        transcricao.append(f"Atendente: {resposta}")

    return "\n".join(transcricao), ultima_resposta


def _rodar_caso(team, caso: EvalCase) -> bool:
    print(f"\n=== Caso: {caso.name} ===")
    transcricao, _ = _rodar_conversa(team, caso.prompts)

    judge = AgentAsJudgeEval(
        name=caso.name,
        criteria=caso.criteria,
        scoring_strategy="binary",
        model=get_specialist_model(),
        print_summary=True,
    )
    resultado = judge.run(input="\n".join(caso.prompts), output=transcricao)

    passou = bool(resultado and resultado.pass_rate >= 100.0)
    print(f"[{'PASSOU' if passou else 'FALHOU'}] {caso.name}")
    return passou


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

    team = criar_equipe()

    resultados = [(caso.name, _rodar_caso(team, caso)) for caso in casos]

    total = len(resultados)
    aprovados = sum(1 for _, ok in resultados if ok)
    taxa = (aprovados / total * 100) if total else 0.0

    print(f"\n=== Resumo: {aprovados}/{total} casos aprovados ({taxa:.1f}%) ===")

    if taxa < PASS_RATE_THRESHOLD:
        sys.exit(1)


if __name__ == "__main__":
    main()
