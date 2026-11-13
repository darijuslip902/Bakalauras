"""GitHub issues rinkimas pagal šaltinių failą (be autentifikacijos).

Pavyzdžiai:
    python -m tools.collect --check      nemokama etikečių patikra (po 1 užklausą šaltiniui)
    python -m tools.collect              pagrindinis rinkimas ('base' šaltiniai)
    python -m tools.collect --augment    tikslinis trūkstamų klasių papildymas
    python -m tools.collect --refresh    surinkti iš naujo ir jau baigtus šaltinius

Baigti šaltiniai (repozitorija + etiketė) įsimenami DB lentelėje collection_progress ir kitą kartą
praleidžiami, todėl po GitHub API limito paleidus tą pačią komandą tęsiama nuo neužbaigto šaltinio.
"""

from pathlib import Path

from app import config
from app.ml import ai_labeling
from app.ml.class_analysis import DEFAULT_TARGET_PER_CLASS, augmentation_plan, class_overview, deficits
from app.ml.collection import SourcesError, check_sources, import_sources, load_sources
import time

from tools._common import backup_database, open_database, parser

DEFAULT_SOURCES = config.PROJECT_DIR / "tools" / "sources.json"


def _token(use_token: bool) -> str | None:
    # Pagal nutylėjimą jokios GitHub paskyros autentifikacijos nenaudojama.
    return config.github_token() if use_token else None


def main(argv: list[str] | None = None, transport: object = None) -> int:
    args_parser = parser("Renka viešus GitHub issues pagal tools/sources.json.")
    args_parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    mode = args_parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="tik patikrinti šaltinius (nieko neįrašo)")
    mode.add_argument("--augment", action="store_true", help="papildyti tik trūkstamas klases")
    args_parser.add_argument("--target", type=int, default=DEFAULT_TARGET_PER_CLASS,
                             help="norimas mokymo pavyzdžių skaičius kiekvienai klasei (--augment)")
    args_parser.add_argument("--refresh", action="store_true",
                             help="nepraleisti jau surinktų šaltinių, o surinkti juos iš naujo")
    args_parser.add_argument("--counts", action="store_true",
                             help="su --check: parodyti ir bendrą issues skaičių (Search API, lėčiau)")
    args_parser.add_argument("--no-backup", action="store_true",
                             help="nekurti DB atsarginės kopijos prieš importą (nerekomenduojama)")
    args_parser.add_argument("--ai-model", default=ai_labeling.DEFAULT_MODEL)
    args_parser.add_argument("--use-token", action="store_true",
                             help="naudoti GITHUB_TOKEN iš .env (pagal nutylėjimą – ne)")
    args = args_parser.parse_args(argv)
    try:
        sources = load_sources(args.sources)
    except SourcesError as exc:
        print(f"KLAIDA: {exc}")
        return 2
    token = _token(args.use_token)

    if args.check:
        all_sources = sources.base + [s for items in sources.augment.values() for s in items]
        unique = list(dict.fromkeys(all_sources))
        print(f"Tikrinama šaltinių: {len(unique)} (GitHub be autentifikacijos leidžia ~60 užklausų per valandą)")
        problems = 0
        pause = (lambda: time.sleep(2.2 if token else 6.5)) if args.counts and transport is None else None
        for item in check_sources(unique, token, transport, with_counts=args.counts, pause=pause):
            source = item["source"]
            mark = "OK " if item["status"] == "ok" else "!! "
            problems += item["status"] != "ok"
            print(f"{mark}{source.repository} [{source.label}]: {item['message']}")
        print("Visi šaltiniai tinkami." if not problems else
              f"Probleminių šaltinių: {problems}. Pataisykite etiketes tools/sources.json arba juos pašalinkite.")
        return 1 if problems else 0

    if not args.no_backup:
        backup = backup_database(args.db)
        if backup:
            print(f"DB atsarginė kopija: {backup}")
    conn = open_database(args.db)
    if args.augment:
        overview = class_overview(conn, args.ai_model, ai_labeling.PROMPT_VERSION, args.target)
        if not overview["dataset"].get("train_rows"):
            print("Dar nėra DI ar žmogaus žymų – pirmiausia atlikite DI žymėjimą (python -m tools.ai_label).")
            conn.close()
            return 2
        shortages = deficits(overview)
        if not shortages:
            print(f"Visoms klasėms jau yra bent {args.target} mokymo pavyzdžių – papildyti nereikia.")
            conn.close()
            return 0
        selected, without_source = augmentation_plan(shortages, sources.augment)
        for field, value in without_source:
            print(f"Klasei {field}:{value} papildymo šaltinio nėra – trūkumas bus parodytas ataskaitoje.")
        if not selected:
            conn.close()
            return 0
        print(f"Papildoma iš {len(selected)} šaltinių (įrašai žymimi source_kind = augmentation; "
              "į bandomąjį ir testavimo rinkinius jie nepatenka).")
        totals = import_sources(conn, selected, "augmentation", token, transport, skip_completed=not args.refresh)
        print("Toliau: python -m tools.ai_label (pažymės tik naujus įrašus), tada python -m tools.class_report.")
    else:
        totals = import_sources(conn, sources.base, "base", token, transport, skip_completed=not args.refresh)
    print(f"Iš viso naujų: {totals['imported']}, atnaujintų: {totals['updated']}, "
          f"praleistų (jau surinktų) šaltinių: {totals['skipped_sources']}, "
          f"nepavykusių šaltinių: {totals['failed_sources']}")
    if totals["failed_sources"]:
        print("Paleiskite tą pačią komandą vėliau – baigti šaltiniai bus praleisti. "
              "Norėdami surinkti viską iš naujo: --refresh.")
    conn.close()
    return 1 if totals["failed_sources"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
