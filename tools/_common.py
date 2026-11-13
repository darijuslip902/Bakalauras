"""Bendra CLI scenarijų pradžia: `.env` nuskaitymas ir DB prisijungimas."""

import argparse
import sqlite3
from datetime import datetime, timezone
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


def backup_database(path: Path | None) -> Path | None:
    """Prieš masinį importą sukuria DB kopiją `<DB aplankas>/backups/` (SQLite backup API).

    Esamas failas nekeičiamas; kiekviena kopija turi laiko žymą. Grąžina kopijos kelią arba
    None, jei DB failo dar nėra (nėra ką kopijuoti).
    """
    config.load_env_file(config.PROJECT_DIR / ".env")
    source_path = path or config.database_path()
    if not source_path.exists():
        return None
    folder = source_path.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target_path = folder / f"{source_path.stem}-{stamp}{source_path.suffix}"
    source = sqlite3.connect(source_path)
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return target_path
