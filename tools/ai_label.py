"""DI žymėjimas per Anthropic Claude API su griežta sąnaudų kontrole.

Numatytasis režimas – DRY-RUN: API nekviečiamas, parodoma, kiek įrašų būtų žymima
ir kiek tai kainuotų. Tikroms (mokamoms) užklausoms reikia --execute.

Pavyzdžiai:
    python -m tools.ai_label --limit 20
    python -m tools.ai_label --limit 20 --max-cost-usd 0.10 --execute
"""

import os

from app.ml import ai_labeling
from tools._common import open_database, parser

DEFAULT_TOTAL_BUDGET_USD = 10.0


def _total_budget() -> float:
    try:
        value = float(os.environ.get("AI_TOTAL_BUDGET_USD", ""))
    except ValueError:
        return DEFAULT_TOTAL_BUDGET_USD
    return value if value > 0 else DEFAULT_TOTAL_BUDGET_USD


def _create_client():
    import anthropic

    # Raktas skaitomas iš ANTHROPIC_API_KEY (.env); niekur nespausdinamas.
    return anthropic.Anthropic(max_retries=3, timeout=60.0)


def main(argv: list[str] | None = None, client: object = None, ask=input) -> int:
    args_parser = parser("Žymi kokybiškus GitHub issues DI modeliu (numatyta – tik dry-run).")
    args_parser.add_argument("--model", default=ai_labeling.DEFAULT_MODEL,
                             choices=sorted(ai_labeling.PRICES_USD_PER_MTOK))
    args_parser.add_argument("--limit", type=int, default=20, help="daugiausia įrašų šiame paleidime")
    args_parser.add_argument("--max-cost-usd", type=float, default=0.50,
                             help="šio paleidimo išlaidų riba USD")
    args_parser.add_argument("--execute", action="store_true",
                             help="iš tikrųjų siųsti mokamas API užklausas")
    args_parser.add_argument("--yes", action="store_true", help="neklausti patvirtinimo")
    args = args_parser.parse_args(argv)
    if args.limit < 1 or args.max_cost_usd <= 0:
        args_parser.error("--limit ir --max-cost-usd turi būti teigiami")

    conn = open_database(args.db)
    total_budget = _total_budget()
    spent = ai_labeling.total_spent_usd(conn)
    issues, summary = ai_labeling.plan(conn, args.model, args.limit)
    print(f"Modelis: {args.model}, prompt versija: {ai_labeling.PROMPT_VERSION}")
    print(f"Atrinkta žymėjimui: {summary.selected} (riba {args.limit})")
    print(f"Tikėtina kaina: ~${summary.expected_cost_usd:.4f}; blogiausiu atveju: ${summary.worst_case_cost_usd:.4f}")
    print(f"Jau išleista (visi paleidimai): ${spent:.4f}; bendras biudžetas: ${total_budget:.2f}; "
          f"šio paleidimo riba: ${args.max_cost_usd:.2f}")

    if not args.execute:
        print("\nDRY-RUN: API nebuvo kviečiamas. Tikram žymėjimui pridėkite --execute.")
        conn.close()
        return 0
    if not issues:
        print("Nėra ką žymėti.")
        conn.close()
        return 0
    if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
        print("KLAIDA: nenustatytas ANTHROPIC_API_KEY (.env faile).")
        conn.close()
        return 2
    if not args.yes and ask("Siųsti MOKAMAS API užklausas? Įrašykite 'taip': ").strip().lower() != "taip":
        print("Atšaukta.")
        conn.close()
        return 1

    summary = ai_labeling.run_labelling(
        conn, client or _create_client(), args.model, args.limit, args.max_cost_usd, total_budget
    )
    print(f"\nPažymėta: {summary.labelled}, netinkamų atsakymų: {summary.invalid}, "
          f"šio paleidimo kaina: ${summary.run_cost_usd:.4f}")
    if summary.stopped_reason:
        print(f"Sustabdyta: {summary.stopped_reason}")
    for error in summary.errors[:10]:
        print(f"  {error}")
    conn.close()
    return 1 if summary.stopped_reason and summary.stopped_reason.startswith("API") else 0


if __name__ == "__main__":
    raise SystemExit(main())
