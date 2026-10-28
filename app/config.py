import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = "data/bakalauras.sqlite3"
DEFAULT_IMPORT_LIMIT = 100


def database_path() -> Path:
    path = Path(os.environ.get("DATABASE_PATH") or DEFAULT_DATABASE_PATH)
    return path if path.is_absolute() else PROJECT_DIR / path


def github_token() -> str | None:
    """Neprivalomas tokenas; skaitomas tik iš aplinkos ir niekur nerodomas."""
    return os.environ.get("GITHUB_TOKEN") or None


def max_import_limit() -> int:
    try:
        value = int(os.environ.get("GITHUB_IMPORT_LIMIT", ""))
    except ValueError:
        return DEFAULT_IMPORT_LIMIT
    return value if value > 0 else DEFAULT_IMPORT_LIMIT
