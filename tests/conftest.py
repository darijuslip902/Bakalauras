"""Bendros testų nuostatos: testai nenaudoja tikrų apmokytų modelių ir neliečia projekto `models/`."""

import pytest


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """6A: prisijungimas skaito naudotojus iš DB. Net jei testas nepakeičia `get_database_path`,
    jis niekada nepasiekia tikros `data/bakalauras.sqlite3` – numatytoji DB yra laikina."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "default-test.sqlite3"))


@pytest.fixture(autouse=True)
def isolated_models_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Numatytas modelių katalogas – tuščias; testai, kuriems reikia modelių, naudoja savo."""
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "no-models"))
