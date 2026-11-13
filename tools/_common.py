"""Bendra CLI scenarijų pradžia: `.env` nuskaitymas ir DB prisijungimas."""

import argparse
import sqlite3
from pathlib import Path

from app import config
from app.db import connect, init_db


def parser(description: str) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=description)
    result.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite failas (numatytasis – DATABASE_PATH arba data/bakalauras.sqlite3)",
    )
    return result


def open_database(path: Path | None) -> sqlite3.Connection:
    config.load_env_file(config.PROJECT_DIR / ".env")
    conn = connect(path or config.database_path())
    init_db(conn)
    return conn
