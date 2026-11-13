"""Bendros testų nuostatos: testai nenaudoja tikrų apmokytų modelių ir neliečia projekto `models/`."""

import pytest


@pytest.fixture(autouse=True)
def isolated_models_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Numatytas modelių katalogas – tuščias; testai, kuriems reikia modelių, naudoja savo."""
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "no-models"))
