"""Naujų klaidų pranešimų automatinis klasifikavimas vietiniais ML modeliais (5C etapas).

- Naudojami `python -m tools.train_models` sukurti failai `models/<laukas>.joblib`; jokių DI API
  užklausų, jokio tinklo.
- Kiekvienas laukas (kategorija, sudėtingumas, prioritetas) turi savo modelį, todėl vieno
  trūkumas ar klaida nesustabdo kitų.
- Trūkstamas ar sugadintas modelis nesukelia svetainės klaidos: prognozė išsaugoma su
  statusu `model_unavailable` / `error` ir aiškiu paaiškinimu.
- Prognozė saugoma lentelėje `prediction_runs` atskirai nuo žmogaus patvirtintų žymų.
- Modelio įvertis (`predict_proba` maksimumas) NĖRA kalibruota tikimybė ir negarantuoja tikslumo.
"""

import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.services.lt_translation import PreparedText, prepare_model_text

logger = logging.getLogger(__name__)

FIELDS = ("category_label", "complexity_label", "priority_label")
METHOD = "TF-IDF + LogisticRegression (įvertis = didžiausia predict_proba reikšmė)"

# Peržiūros slenksčiai: įvertis žemiau slenksčio -> „Rekomenduojama peržiūra“. Skirtingi laukai
# turi skirtingą klasių skaičių (kategorija 8, kiti 3), todėl vieno bendro slenksčio nėra.
# Parinkta pagal 112 testo įrašų (žr. docs/EVALUATION_PLAN.md): tai orientacinė, ne patikrinta riba.
REVIEW_THRESHOLDS = {"category_label": 0.40, "complexity_label": 0.60, "priority_label": 0.60}

FIELD_FILES = {field: f"{field}.joblib" for field in FIELDS}
_ALLOWED = {
    "category_label": config.CATEGORY_LABELS,
    "complexity_label": config.COMPLEXITY_LABELS,
    "priority_label": config.PRIORITY_LABELS,
}


def model_text(title: str, description: str) -> str:
    """Modelio įvestis: kaip mokymo metu (`issue_text` modulyje `data_quality`) – pavadinimas + aprašymas.

    Sąmoningai nekopijuojama importu: svetainės kodas neimportuoja ML mokymo / DI modulių
    (tai tikrina testas `test_website_does_not_import_ai_or_training_modules`).
    """
    return f"{title.strip()}\n\n{(description or '').strip()}".strip()


@dataclass(frozen=True)
class FieldPrediction:
    field: str
    status: str  # ok | model_unavailable | error
    label: str | None = None
    score: float | None = None
    needs_review: bool = False
    model_version: str | None = None
    message: str | None = None
    input_language: str | None = None  # lt | en
    translation_method: str | None = None  # none | glossary | unavailable


class Predictor:
    """Įkelia modelius pagal poreikį ir talpina juos atmintyje (iš naujo – pakeitus failą)."""

    def __init__(self, models_dir: Path) -> None:
        self.models_dir = Path(models_dir)
        self._cache: dict[str, tuple[tuple[int, int], dict | None, str | None]] = {}
        self._lock = threading.Lock()

    def _load(self, field: str) -> tuple[dict | None, str | None]:
        """Grąžina (modelio paketas, None) arba (None, klaidos aprašymas); niekada nemeta klaidos."""
        path = self.models_dir / FIELD_FILES[field]
        try:
            stat = path.stat()
        except OSError:
            return None, (f"Modelio failas {path.name} nerastas. "
                          "Jį sukuria komanda: python -m tools.train_models")
        signature = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            cached = self._cache.get(field)
            if cached and cached[0] == signature:
                return cached[1], cached[2]
            bundle: dict | None = None
            problem: str | None = None
            try:
                import joblib

                loaded = joblib.load(path)
                if loaded.get("field") != field or not hasattr(loaded["pipeline"], "predict_proba"):
                    raise ValueError("netinkamas modelio failo turinys")
                bundle = loaded
            except Exception as exc:  # sugadintas failas, nesuderinama scikit-learn versija ir pan.
                logger.warning("Nepavyko įkelti modelio %s: %s", path.name, type(exc).__name__)
                problem = (f"Modelio failo {path.name} nepavyko įkelti ({type(exc).__name__}). "
                           "Perkurkite modelius: python -m tools.train_models")
            self._cache[field] = (signature, bundle, problem)
        return bundle, problem

    def predict(self, title: str, description: str) -> list[FieldPrediction]:
        prepared = prepare_model_text(title, description)
        return [self._predict_field(field, prepared) for field in FIELDS]

    def _predict_field(self, field: str, prepared: PreparedText) -> FieldPrediction:
        language = (prepared.language, prepared.method)
        bundle, problem = self._load(field)
        if bundle is None:
            return FieldPrediction(field, "model_unavailable", message=problem,
                                   input_language=language[0], translation_method=language[1])
        version = str(bundle.get("model_version") or "")
        try:
            pipeline = bundle["pipeline"]
            probabilities = pipeline.predict_proba([prepared.text])[0]
            index = int(probabilities.argmax())
            label = str(pipeline.classes_[index])
            score = float(probabilities[index])
            if label not in _ALLOWED[field]:
                raise ValueError("nežinoma klasė")
        except Exception as exc:
            logger.warning("Prognozė nepavyko (%s): %s", field, type(exc).__name__)
            return FieldPrediction(field, "error", model_version=version,
                                   message=f"Prognozės apskaičiuoti nepavyko ({type(exc).__name__}).",
                                   input_language=language[0], translation_method=language[1])
        # Lietuviško teksto prognozė su per maža vertimo aprėptimi visada žymima kaip nepatikima.
        needs_review = score < REVIEW_THRESHOLDS[field] or not prepared.reliable
        return FieldPrediction(field, "ok", label, score, needs_review, version, prepared.note,
                               language[0], language[1])


_predictors: dict[Path, Predictor] = {}


def default_predictor() -> Predictor:
    """Bendras kiekvienam modelių katalogui (kad modeliai nebūtų įkeliami kiekvienos užklausos metu)."""
    path = config.models_dir()
    return _predictors.setdefault(path, Predictor(path))


def save_predictions(conn: sqlite3.Connection, report_id: int, predictions: list[FieldPrediction]) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        conn.executemany(
            "INSERT INTO prediction_runs (bug_report_id, field, status, predicted_label, score, needs_review,"
            " method, model_version, message, created_at, input_language, translation_method)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(report_id, p.field, p.status, p.label, p.score, int(p.needs_review),
              METHOD if p.status == "ok" else None, p.model_version, p.message, now,
              p.input_language, p.translation_method) for p in predictions],
        )


def classify_report(conn: sqlite3.Connection, predictor: Predictor, report_id: int) -> list[FieldPrediction]:
    """Paleidžia modelius pranešimui ir išsaugo rezultatą. Žmogaus žymų nekeičia."""
    report = conn.execute("SELECT title, description FROM bug_reports WHERE id = ?", (report_id,)).fetchone()
    if report is None:
        raise LookupError("pranešimas nerastas")
    predictions = predictor.predict(report["title"], report["description"])
    save_predictions(conn, report_id, predictions)
    return predictions


def latest_predictions(conn: sqlite3.Connection, report_id: int) -> dict[str, sqlite3.Row]:
    """Naujausia kiekvieno lauko prognozė (laukas -> eilutė)."""
    rows = conn.execute(
        "SELECT * FROM prediction_runs WHERE id IN "
        "(SELECT MAX(id) FROM prediction_runs WHERE bug_report_id = ? GROUP BY field)",
        (report_id,),
    )
    return {row["field"]: row for row in rows}
