"""Klasių pasiskirstymo ir trūkumų ataskaita visoms trims užduotims + bandomojo rinkinio DI kokybė.

Pavyzdys:
    python -m tools.class_report
"""

from app.ml import ai_labeling
from app.ml.class_analysis import DEFAULT_TARGET_PER_CLASS, class_overview, deficits, pilot_agreement
from app.ml.training import FIELDS
from tools._common import open_database, parser

TITLES = {"category_label": "Kategorija", "complexity_label": "Sudėtingumas", "priority_label": "Prioritetas"}


def main(argv: list[str] | None = None) -> int:
    args_parser = parser("Parodo kiekvienos klasės pavyzdžių skaičių ir trūkumus.")
    args_parser.add_argument("--ai-model", default=ai_labeling.DEFAULT_MODEL)
    args_parser.add_argument("--target", type=int, default=DEFAULT_TARGET_PER_CLASS,
                             help="norimas mokymo pavyzdžių skaičius kiekvienai klasei")
    args = args_parser.parse_args(argv)
    conn = open_database(args.db)
    overview = class_overview(conn, args.ai_model, ai_labeling.PROMPT_VERSION, args.target)
    print(f"Mokymo įrašų (tinka, visos 3 žymos, be testavimo rinkinio): {overview['dataset'].get('train_rows', 0)}; "
          f"testo įrašų su etalonu (žmogaus arba DI): {overview['dataset'].get('human_test_rows', 0)}")
    for field in FIELDS:
        print(f"\n{TITLES[field]} (tikslas: {args.target} mokymo pavyzdžių klasei)")
        print(f"  {'Klasė':28} {'Mokymui':>8} {'Testui':>7}  Būsena")
        for item in overview["fields"][field]:
            state = "OK" if not item["missing"] else f"TRŪKSTA {item['missing']}"
            print(f"  {item['value']:28} {item['train']:>8} {item['test']:>7}  {state}")

    shortages = deficits(overview)
    if shortages:
        print(f"\nKlasių su trūkumu: {len(shortages)}. Papildyti galima: python -m tools.collect --augment "
              f"--target {args.target}")
        print("Pastaba: klasės nepriskiriamos dirbtinai – jei po papildymo pavyzdžių vis tiek nepakaks, "
              "tai bus nurodyta mokymo ataskaitoje kaip apribojimas.")
    else:
        print("\nVisoms klasėms pavyzdžių pakanka.")

    pilot = pilot_agreement(conn, args.ai_model, ai_labeling.PROMPT_VERSION)
    print(f"\nBandomasis rinkinys ({args.ai_model}): įrašų {pilot['pilot_total']}, palyginta su žmogumi {pilot['compared']}")
    if pilot["suitability"]:
        print(f"  Tinkamumas mokymui: sutapimas {pilot['suitability']['accuracy']:.3f}")
        for field in FIELDS:
            metrics = pilot["fields"][field]
            if metrics:
                print(f"  {TITLES[field]}: sutapimas {metrics['accuracy']:.3f}, macro-F1 {metrics['macro_f1']:.3f} "
                      f"({metrics['samples']} įrašai)")
    else:
        print("  Palyginimo dar nėra: pažymėkite bandomąjį rinkinį svetainėje ir paleiskite "
              "python -m tools.ai_label --subset pilot --execute")
    measured = ai_labeling.measured_cost_per_request(conn, args.ai_model)
    if measured:
        print(f"  Faktinė vidutinė užklausos kaina: ${measured[0]:.5f} ({measured[1]} užklausų)")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
