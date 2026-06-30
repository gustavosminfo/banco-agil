"""
scripts/sync_to_studio.py
Publica os agentes e o Team do Banco Ágil no banco do AgentOS para que
apareçam como componentes editáveis na lista do Studio (os.agno.com).

Uso:
    # Banco local (Docker)
    source .venv/bin/activate
    python scripts/sync_to_studio.py

    # Banco Railway (produção) — requer EVAL_DB_URL no .env
    python scripts/sync_to_studio.py --remote

O script é idempotente: re-executar salva uma nova versão sem apagar as
anteriores. Use labels descritivos para identificar cada publicação
(ex.: "v1-from-code", "v2-improved-triagem").

Após a execução, acesse os.agno.com → Studio → Agents/Teams para ver e
testar os componentes. Use docs/adopt-from-studio.md para importar
melhorias feitas no Studio de volta ao código.
"""

import argparse
import sys
from pathlib import Path

# Garante que o projeto está no path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from banco_agil.config import DB_URL, EVAL_DB_URL
from banco_agil.agents import triagem_agent, credito_agent, entrevista_agent, cambio_agent
from banco_agil.team import criar_equipe
from agno.db.postgres import PostgresDb


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica agentes do Banco Ágil no Studio.")
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Usa EVAL_DB_URL (banco Railway) em vez do banco local.",
    )
    parser.add_argument(
        "--label",
        default="from-code",
        help="Label da versão publicada (default: 'from-code').",
    )
    args = parser.parse_args()

    if args.remote:
        if not EVAL_DB_URL:
            print("ERRO: EVAL_DB_URL não está configurada no .env.")
            print("      Configure DATABASE_PUBLIC_URL do Railway como EVAL_DB_URL.")
            sys.exit(1)
        db_url = EVAL_DB_URL
        destino = "Railway (remoto)"
    else:
        db_url = DB_URL
        destino = "Local (Docker)"

    print(f"\nBanco de destino: {destino}")
    print(f"Label da versão:  {args.label!r}")
    print("-" * 50)

    db = PostgresDb(db_url=db_url)

    agentes = [
        ("Agente de Triagem",            triagem_agent),
        ("Agente de Crédito",            credito_agent),
        ("Agente de Entrevista",         entrevista_agent),
        ("Agente de Câmbio",             cambio_agent),
    ]

    # ── Agents ────────────────────────────────────────────────────────────────
    for nome, agente in agentes:
        try:
            version = agente.save(db=db, label=args.label)
            print(f"  OK {nome:35} versao {version}")
        except Exception as e:
            print(f"  ERRO {nome:35} {e}")

    # ── Team ──────────────────────────────────────────────────────────────────
    # team.save() salva os agentes-membros internamente; usar o mesmo label dos
    # saves individuais acima causaria colisão ("Label already exists").
    try:
        team = criar_equipe()
        version = team.save(db=db, label=f"{args.label}-team")
        print(f"  OK {'Team Banco Agil':35} versao {version}")
    except Exception as e:
        print(f"  ERRO {'Team Banco Agil':35} {e}")

    print("-" * 50)
    print("Concluido. Abra os.agno.com -> Studio para ver os componentes.")
    print("Use docs/adopt-from-studio.md para importar melhorias de volta ao codigo.")


if __name__ == "__main__":
    main()
