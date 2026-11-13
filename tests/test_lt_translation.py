"""5C: lietuvių kalbos aptikimas ir žodynu pagrįstas vertimas prieš klasifikavimą."""

from app.services.lt_translation import detect_language, prepare_model_text, translate_to_english

LT_TITLE = "Mygtukas neveikia"
LT_TEXT = "Paspaudus mygtuką „Išsaugoti“ puslapis užstringa ir pasirodo klaida 500."
EN_TITLE = "Save button does not work"
EN_TEXT = "Clicking the save button freezes the page and shows error 500."


def test_detects_languages() -> None:
    assert detect_language(f"{LT_TITLE} {LT_TEXT}") == "lt"
    assert detect_language(f"{EN_TITLE} {EN_TEXT}") == "en"
    assert detect_language("") == "en"


def test_english_text_is_not_translated() -> None:
    prepared = prepare_model_text(EN_TITLE, EN_TEXT)

    assert (prepared.language, prepared.method, prepared.reliable) == ("en", "none", True)
    assert prepared.text == f"{EN_TITLE}\n\n{EN_TEXT}"


def test_lithuanian_text_is_translated_to_english_terms() -> None:
    prepared = prepare_model_text(LT_TITLE, LT_TEXT)

    assert prepared.language == "lt" and prepared.method == "glossary"
    assert prepared.reliable and prepared.terms >= 3
    for word in ("button", "error", "500"):
        assert word in prepared.text
    assert "mygtuk" not in prepared.text.lower()
    assert prepared.note and "lietuvių" in prepared.note


def test_translation_is_deterministic_and_does_not_modify_input() -> None:
    first = prepare_model_text(LT_TITLE, LT_TEXT)

    assert prepare_model_text(LT_TITLE, LT_TEXT) == first
    assert translate_to_english(LT_TEXT) == translate_to_english(LT_TEXT)


def test_few_recognised_terms_are_flagged_unreliable() -> None:
    prepared = prepare_model_text("Labas", "Šiandien labai gražus oras ir gera nuotaika")

    assert prepared.language == "lt" and not prepared.reliable
    assert "nepatikima" in (prepared.note or "")


def test_translation_failure_falls_back_to_original_and_is_unreliable(monkeypatch) -> None:
    from app.services import lt_translation

    def boom(text: str):
        raise RuntimeError("vertimas neprieinamas")

    monkeypatch.setattr(lt_translation, "translate_to_english", boom)

    prepared = lt_translation.prepare_model_text(LT_TITLE, LT_TEXT)

    assert prepared.method == "unavailable" and not prepared.reliable
    assert LT_TITLE in prepared.text  # naudojamas originalus tekstas
    assert "nepavyko" in (prepared.note or "")
