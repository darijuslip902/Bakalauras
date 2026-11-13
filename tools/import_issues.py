"""Masinis viešų GitHub issues importas iš kelių repozitorijų (tik skaitymas).

Pavyzdys:
    python -m tools.import_issues --repo pallets/flask --repo psf/requests --limit 500 --label bug
"""

from app import config
from app.services.github_client import GitHubError, InvalidRepositoryError
from app.services.import_service import run_import
from tools._common import open_database, parser

MAX_LIMIT_PER_REPO = 1000  # GitHub klientas skaito iki 10 puslapių po 100


def main(argv: list[str] | None = None, transport: object = None) -> int:
    args_parser = parser("Importuoja viešus GitHub issues į github_issues lentelę.")
    args_parser.add_argument("--repo", action="append", required=True, help="owner/repo (galima kartoti)")
    args_parser.add_argument("--limit", type=int, default=300, help=f"įrašų kiekis vienai repozitorijai (1–{MAX_LIMIT_PER_REPO})")
    args_parser.add_argument("--label", default=None, help='GitHub etikečių filtras, pvz. "bug"')
    args = args_parser.parse_args(argv)
    if not 1 <= args.limit <= MAX_LIMIT_PER_REPO:
        args_parser.error(f"--limit turi būti nuo 1 iki {MAX_LIMIT_PER_REPO}")

    conn = open_database(args.db)
    failures = 0
    for repository in args.repo:
        try:
            result = run_import(conn, repository, args.limit, config.github_token(), transport, args.label)
        except (InvalidRepositoryError, GitHubError, ValueError) as exc:
            failures += 1
            print(f"{repository}: KLAIDA – {getattr(exc, 'message', exc)}")
            continue
        print(
            f"{repository}: nauji {result.imported}, atnaujinti {result.updated}, "
            f"praleisti PR {result.skipped_pull_requests}, nepavyko {result.failed}"
        )
    conn.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
