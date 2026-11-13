"""Duomenų kokybės ir žymėjimo eigos ataskaita.

Pavyzdys:
    python -m tools.check_data
"""

from app.ml.ai_labeling import spending_report
from app.ml.data_quality import MIN_BODY_CHARS, quality_report
from tools._common import open_database, parser


def main(argv: list[str] | None = None) -> int:
    args = parser("Parodo importuotų issues kokybę, testavimo rinkinį ir DI žymėjimo sąnaudas.").parse_args(argv)
    conn = open_database(args.db)
    rows = quality_report(conn)
    columns = ("total", "ok", "short", "duplicate", "excluded_label", "augmentation", "pilot_set", "test_set",
               "human_complete", "ai_labelled")
    print(f"{'Repozitorija':30} " + " ".join(f"{c:>14}" for c in columns))
    totals = dict.fromkeys(columns, 0)
    for row in rows:
        print(f"{row['repository']:30} " + " ".join(f"{row[c]:>14}" for c in columns))
        for column in columns:
            totals[column] += row[column]
    print(f"{'IŠ VISO':30} " + " ".join(f"{totals[c]:>14}" for c in columns))
    print(
        f"\nok – tinka DI žymėjimui; short – aprašymas trumpesnis nei {MIN_BODY_CHARS} simbolių; "
        "duplicate – pasikartojantis tekstas; excluded_label – GitHub etiketė rodo ne klaidą; "
        "augmentation – importuota papildymo metu; pilot_set – bandomasis rinkinys; "
        "test_set – žmogaus testavimo rinkinys; "
        "human_complete – žmogus pažymėjo visus 3 laukus; ai_labelled – yra sėkminga DI žyma."
    )
    spending = spending_report(conn)
    if spending:
        print("\nDI žymėjimas:")
        for item in spending:
            print(
                f"  {item['model']} / {item['prompt_version']}: įrašų {item['rows']}, ok {item['ok']}, "
                f"klaidų {item['invalid']}, tinka mokymui {item['suitable']}, "
                f"tokenai in {item['input_tokens']} / out {item['output_tokens']} / "
                f"cache read {item['cache_read_tokens']}, kaina ${item['cost_usd']:.4f}"
            )
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
