"""DI žymėjimas per Anthropic Claude API su griežta sąnaudų kontrole.

Numatytasis režimas – DRY-RUN: API nekviečiamas, parodoma, kiek įrašų būtų žymima
ir kiek tai kainuotų. Tikroms (mokamoms) užklausoms reikia --execute.

Pavyzdžiai:
    python -m tools.ai_label --limit 20
    python -m tools.ai_label --subset test --limit 120 --max-cost-usd 0.20 --execute
    python -m tools.ai_label --subset training --limit 3000 --workers 4 --execute

Paleidimas tęstinis: jau pažymėti įrašai praleidžiami, todėl po nutraukimo (Ctrl+C, klaida,
limitas) pakanka paleisti tą pačią komandą dar kartą.
"""

import os

from app.ml import ai_labeling
from tools._common import open_database, parser

DEFAULT_TOTAL_BUDGET_USD = 10.0
MAX_WORKERS = 8


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


def _print_status(conn, model: str) -> None:
    print("Pažanga (tik kokybės patikrą praėję įrašai):")
    for name, item in ai_labeling.subset_status(conn, model, ai_labeling.PROMPT_VERSION).items():
        print(f"  {name:<9} iš viso {item['total']:>5}, pažymėta {item['labelled']:>5}, "
              f"nepavyko {item['failed']:>3}, liko {item['remaining']:>5}")


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
    args_parser.add_argument("--subset", choices=("all", "pilot", "test", "training"), default="all",
                             help="pilot – tik bandomasis rinkinys; training – be bandomojo ir testavimo")
    args_parser.add_argument("--workers", type=int, default=1,
                             help=f"lygiagrečių užklausų skaičius (1–{MAX_WORKERS}, numatyta 1)")
    args = args_parser.parse_args(argv)
    if args.limit < 1 or args.max_cost_usd <= 0:
        args_parser.error("--limit ir --max-cost-usd turi būti teigiami")
    if not 1 <= args.workers <= MAX_WORKERS:
        args_parser.error(f"--workers turi būti nuo 1 iki {MAX_WORKERS}")

    conn = open_database(args.db)
    total_budget = _total_budget()
    spent = ai_labeling.total_spent_usd(conn)
    subset = None if args.subset == "all" else args.subset
    issues, summary = ai_labeling.plan(conn, args.model, args.limit, subset)
    print(f"Modelis: {args.model}, prompt versija: {ai_labeling.PROMPT_VERSION}, rinkinys: {args.subset}")
    print(f"Atrinkta žymėjimui: {summary.selected} (riba {args.limit})")
    print(f"Teorinis kainos įvertis: ~${summary.expected_cost_usd:.4f}; blogiausiu atveju: "
          f"${summary.worst_case_cost_usd:.4f}")
    measured = ai_labeling.measured_cost_per_request(conn, args.model)
    if measured:
        print(f"Pagal faktines {measured[1]} užklausas: ~${measured[0]:.5f} įrašui, "
              f"~${measured[0] * summary.selected:.4f} šiems {summary.selected} įrašams (įvertis, ne garantija)")
    else:
        print("Faktinės kainos dar nėra: ją parodys pirmas tikras (bandomasis) paleidimas.")
    print(f"Jau išleista (visi paleidimai): ${spent:.4f}; bendras biudžetas: ${total_budget:.2f}; "
          f"šio paleidimo riba: ${args.max_cost_usd:.2f}")

    _print_status(conn, args.model)

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
        conn, client or _create_client(), args.model, args.limit, args.max_cost_usd, total_budget,
        subset=subset, workers=args.workers,
    )
    print(f"\nPažymėta: {summary.labelled}, netinkamų atsakymų: {summary.invalid}, "
          f"šio paleidimo kaina: ${summary.run_cost_usd:.4f}")
    if summary.stopped_reason:
        print(f"Sustabdyta: {summary.stopped_reason}")
    for error in summary.errors[:10]:
        print(f"  {error}")
    _print_status(conn, args.model)
    conn.close()
    return 1 if summary.stopped_reason and summary.stopped_reason.startswith("API") else 0


if __name__ == "__main__":
    raise SystemExit(main())
