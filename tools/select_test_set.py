"""Atsitiktinė žmogaus testavimo rinkinio atranka.

Pažymėtus įrašus žmogus žymi svetainėje („Mokymo duomenys“, mygtukas „Kitas nepažymėtas“
juos pasiūlo pirmus). Šie įrašai niekada nenaudojami mokymui.

Pavyzdys:
    python -m tools.select_test_set --size 200
"""

from app.ml.data_quality import select_test_set
from tools._common import open_database, parser


def main(argv: list[str] | None = None) -> int:
    args_parser = parser("Atsitiktinai atrenka žmogaus testavimo rinkinį.")
    args_parser.add_argument("--size", type=int, default=200, help="norimas rinkinio dydis iš viso")
    args_parser.add_argument("--seed", type=int, default=42, help="atsitiktinumo seed (atkartojamumui)")
    args = args_parser.parse_args(argv)
    if args.size < 1:
        args_parser.error("--size turi būti teigiamas")
    conn = open_database(args.db)
    added = select_test_set(conn, args.size, args.seed)
    total = conn.execute("SELECT COUNT(*) FROM github_issues WHERE is_test_set = 1").fetchone()[0]
    print(f"Pridėta į testavimo rinkinį: {added}. Iš viso testavimo rinkinyje: {total}.")
    if total < args.size:
        print("Įspėjimas: kokybiškų įrašų nepakanka norimam dydžiui.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
