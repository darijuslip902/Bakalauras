"""Visi nemokami 5B žingsniai viena komanda.

1. pagrindinis rinkimas pagal tools/sources.json (be autentifikacijos);
2. kokybės patikra ir filtravimas;
3. bandomojo ir galutinio testavimo rinkinių atranka (prieš DI žymėjimą);
4. DI žymėjimo kainos įvertis (dry-run, API nekviečiamas);
5. tolesnių komandų sąrašas.

Pavyzdys:
    python -m tools.pipeline
"""

from app.ml import ai_labeling
from app.ml.data_quality import check_quality, select_pilot_set, select_test_set
from tools import collect
from tools._common import open_database, parser


def main(argv: list[str] | None = None, transport: object = None) -> int:
    args_parser = parser("Atlieka visus nemokamus duomenų paruošimo žingsnius.")
    args_parser.add_argument("--skip-import", action="store_true", help="neimportuoti iš GitHub")
    args_parser.add_argument("--pilot-size", type=int, default=30)
    args_parser.add_argument("--test-size", type=int, default=120)
    args_parser.add_argument("--seed", type=int, default=42)
    args_parser.add_argument("--model", default=ai_labeling.DEFAULT_MODEL,
                             choices=sorted(ai_labeling.PRICES_USD_PER_MTOK))
    args = args_parser.parse_args(argv)
    db_args = ["--db", str(args.db)] if args.db else []

    print("== 1. Rinkimas iš GitHub ==")
    if args.skip_import:
        print("Praleista (--skip-import).")
    else:
        collect.main(db_args, transport=transport)

    conn = open_database(args.db)
    quality = check_quality(conn)
    print("\n== 2. Kokybės patikra ==")
    print(f"Tinkami: {len(quality.ok_ids)}; atmesta – trumpi: {len(quality.short_body_ids)}, "
          f"dublikatai: {len(quality.duplicate_ids)}, ne klaidų etiketės: {len(quality.excluded_label_ids)}")

    print("\n== 3. Bandomasis ir testavimo rinkiniai ==")
    added_test = select_test_set(conn, args.test_size, args.seed)  # galutinis testas – pirmas
    added_pilot = select_pilot_set(conn, args.pilot_size, args.seed)
    pilot = conn.execute("SELECT COUNT(*) FROM github_issues WHERE is_pilot_set = 1").fetchone()[0]
    test = conn.execute("SELECT COUNT(*) FROM github_issues WHERE is_test_set = 1").fetchone()[0]
    print(f"Bandomasis: {pilot} (nauji {added_pilot}); testavimo: {test} (nauji {added_test}).")

    print("\n== 4. DI žymėjimo kainos įvertis (dry-run) ==")
    for subset, title in (("pilot", "bandomasis rinkinys"), (None, "visi tinkami įrašai")):
        _, summary = ai_labeling.plan(conn, args.model, 100_000, subset)
        print(f"{title}: {summary.selected} įrašų, teorinis įvertis ~${summary.expected_cost_usd:.2f} "
              f"(blogiausiu atveju ${summary.worst_case_cost_usd:.2f})")
    measured = ai_labeling.measured_cost_per_request(conn, args.model)
    if measured:
        print(f"Pagal faktines {measured[1]} užklausas: ~${measured[0]:.5f} vienam įrašui.")
    else:
        print("Faktinės kainos dar nėra – ją parodys bandomasis paleidimas.")
    conn.close()

    print("\n== Kiti žingsniai ==")
    print("1. Svetainėje „Mokymo duomenys“ pažymėkite bandomąjį rinkinį (mygtukas „Kitas nepažymėtas“ jį siūlo pirmą).")
    print("2. MOKAMAS bandymas (tik gavus leidimą): python -m tools.ai_label --subset pilot --limit 40 --execute")
    print("3. Palyginimas ir faktinė kaina: python -m tools.class_report")
    print("4. Pažymėkite testavimo rinkinį svetainėje (toliau „Kitas nepažymėtas“).")
    print("5. MOKAMAS masinis žymėjimas: python -m tools.ai_label --limit 4000 --max-cost-usd 3 --execute")
    print("6. Klasių trūkumai: python -m tools.class_report, jei reikia – python -m tools.collect --augment "
          "ir vėl 5 žingsnis")
    print("7. Mokymas ir ataskaita: python -m tools.train_models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
