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


def load_env_file(path: Path) -> None:
    """Nuskaito paprastą KEY=VALUE `.env` failą, jei jis yra.

    Jau nustatyti aplinkos kintamieji neperrašomi, todėl jie turi pirmenybę.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


# Žymų reikšmės (ARCHITECTURE.md 7 skyrius) ir jų pavadinimai sąsajoje.
STATUS_LABELS = {
    "new": "Nauja",
    "in_progress": "Taisoma",
    "resolved": "Išspręsta",
}
CATEGORY_LABELS = {
    "ui": "Naudotojo sąsaja",
    "backend_api": "Serveris / API",
    "database_data": "Duomenų bazė / duomenys",
    "security": "Saugumas",
    "performance": "Našumas",
    "build_deployment": "Kompiliavimas / diegimas",
    "documentation": "Dokumentacija",
    "other": "Kita",
}
COMPLEXITY_LABELS = {
    "low": "Mažas",
    "medium": "Vidutinis",
    "high": "Didelis",
}
PRIORITY_LABELS = {
    "P0_critical": "P0 – kritinis",
    "P1_high": "P1 – aukštas",
    "P2_medium": "P2 – vidutinis",
    "P3_low": "P3 – žemas",
}

# Mokymo duomenų žymėjimas (4 etapas).
TRAINING_SUITABILITY_LABELS = {
    "unreviewed": "Neįvertinta",
    "suitable": "Tinka mokymui",
    "unsuitable": "Netinka mokymui",
}
ANNOTATION_STATUS_LABELS = {
    "unlabeled": "Nepažymėta",
    "partial": "Iš dalies pažymėta",
    "complete": "Pažymėta",
}
