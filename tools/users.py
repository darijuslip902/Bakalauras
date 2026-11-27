"""6A: naudotojų paskyrų administravimas iš komandinės eilutės (be HTTP registracijos eskalavimo).

Pavyzdžiai (Windows CMD, projekto kataloge, aktyvavus .venv):
    python -m tools.users bootstrap-admin          # perkelia .env administratorių į users (idempotentiška)
    python -m tools.users list
    python -m tools.users set-role jonas developer  # tester | developer | admin
    python -m tools.users deactivate jonas
    python -m tools.users activate jonas
    python -m tools.users set-password jonas       # slaptažodis įvedamas paslėptai

Prieš pirmą `bootstrap-admin` automatiškai sukuriama DB atsarginė kopija (`data/backups/`).
Pakeitus rolę, aktyvumą ar slaptažodį, tai galioja iš karto (sesijos tikrinamos DB).
"""

import getpass
import sys

from app.auth import MIN_PASSWORD_LENGTH, get_auth_settings
from app.services.user_service import (
    ROLES,
    AdminBootstrap,
    bootstrap_admin,
    list_users,
    set_active,
    set_password,
    set_role,
)
from tools._common import backup_database, open_database, parser

_BOOTSTRAP_MESSAGES = {
    AdminBootstrap.CREATED: "Administratorius perkeltas į users lentelę (tas pats vardas ir slaptažodis).",
    AdminBootstrap.EXISTS: "Administratorius jau yra users lentelėje – niekas nepakeista.",
    AdminBootstrap.CONFLICT: (
        "KONFLIKTAS: vardas ADMIN_USERNAME jau priklauso ne administratoriaus paskyrai. Niekas nepakeista. "
        "Pakeiskite ADMIN_USERNAME .env faile arba suteikite rolę: python -m tools.users set-role <vardas> admin"
    ),
    AdminBootstrap.NOT_CONFIGURED: (
        "KLAIDA: .env faile nenustatyti ADMIN_USERNAME, ADMIN_PASSWORD_HASH ir SESSION_SECRET_KEY "
        "(žr. README)."
    ),
}


def main(argv: list[str] | None = None) -> int:
    args_parser = parser("Naudotojų paskyrų administravimas (6A).")
    commands = args_parser.add_subparsers(dest="command", required=True)
    commands.add_parser("bootstrap-admin", help="perkelti .env administratorių į users")
    commands.add_parser("list", help="parodyti naudotojus (be slaptažodžių maišų)")
    role = commands.add_parser("set-role", help="pakeisti naudotojo rolę")
    role.add_argument("username")
    role.add_argument("role", choices=ROLES)
    for name in ("activate", "deactivate", "set-password"):
        commands.add_parser(name).add_argument("username")
    args = args_parser.parse_args(argv)

    if args.command == "bootstrap-admin":
        backup = backup_database(args.db)
        if backup:
            print(f"DB atsarginė kopija: {backup}")
    conn = open_database(args.db)  # užkrauna .env ir saugiai papildo schemą
    try:
        if args.command == "bootstrap-admin":
            result = bootstrap_admin(conn, get_auth_settings())
            print(_BOOTSTRAP_MESSAGES[result])
            return 0 if result in (AdminBootstrap.CREATED, AdminBootstrap.EXISTS) else 2
        if args.command == "list":
            for user in list_users(conn):
                state = "aktyvi" if user.is_active else "išjungta"
                print(f"{user.id:>4}  {user.username:<30} {user.role:<10} {state:<9} {user.email or '-'}")
            return 0
        if args.command == "set-role":
            user = set_role(conn, args.username, args.role)
        elif args.command in ("activate", "deactivate"):
            user = set_active(conn, args.username, args.command == "activate")
        else:
            password = getpass.getpass("Naujas slaptažodis: ")
            if len(password) < MIN_PASSWORD_LENGTH:
                print(f"KLAIDA: slaptažodis turi būti bent {MIN_PASSWORD_LENGTH} simbolių.")
                return 2
            if getpass.getpass("Pakartokite slaptažodį: ") != password:
                print("KLAIDA: slaptažodžiai nesutampa.")
                return 2
            user = set_password(conn, args.username, password)
        if user is None:
            print(f"KLAIDA: naudotojas '{args.username}' nerastas.")
            return 1
        state = "aktyvi" if user.is_active else "išjungta"
        print(f"Atnaujinta: {user.username} – rolė {user.role}, paskyra {state}.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
