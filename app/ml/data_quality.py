"""GitHub issues kokybės patikra ir atranka DI žymėjimui, bandomajam bei testavimo rinkiniui.

Taisyklės paprastos ir dokumentuotos (README, docs/DATA_LABELING.md):
- pasikartojantis tekstas – dublikatai iškreiptų mokymą ir vertinimą;
- GitHub etiketė rodo, kad tai ne klaida (funkcijos pasiūlymas, klausimas, dublikatas...)
  – toks įrašas nesiunčiamas į mokamą DI API;
- per trumpas aprašymas – iš jo neįmanoma nustatyti klaidos pobūdžio;
- pull request įrašai importo metu jau atmesti.
"""

import hashlib
import json
import random
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass

MIN_BODY_CHARS = 30

# Etiketės dalys (mažosiomis raidėmis), rodančios, kad įrašas nėra programinės įrangos klaida.
# „documentation“ sąmoningai neįtraukta – dokumentacijos klaidos yra atskira kategorija.
EXCLUDED_LABEL_KEYWORDS = (
    "enhancement",
    "feature",
    "question",
    "duplicate",
    "invalid",
    "wontfix",
    "won't fix",
    "not a bug",
    "not-a-bug",
    "support",
    "discussion",
    "proposal",
)

# Nekenksmingos frazės: pašalinamos prieš raktažodžių paiešką, nes jos rodo komponentą ar
# darbo būseną, o ne tai, kad įrašas nėra klaida (pvz. „feature: files“, „Needs Discussion“,
# „OS-unsupported“). Tikros ne klaidų etiketės („Feature Request“, „enhancement“,
# „question“, „duplicate“...) lieka atmetamos.
_BENIGN_LABEL_PATTERNS = (
    re.compile(r"^\W*feature\s*:"),  # komponento etiketė „feature: ...“
    re.compile(r"\b(?:needs?|under|pending|requires?|awaiting|in)[\s_-]*discussion\b"),
    re.compile(r"\b(?:un|non-?)?supported\b"),
)

_WHITESPACE_RE = re.compile(r"\s+")


def issue_text(title: str, body: str | None) -> str:
    """Deterministinis modelio įvesties tekstas: pavadinimas + aprašymas."""
    return f"{title.strip()}\n\n{(body or '').strip()}".strip()


def text_fingerprint(title: str, body: str | None) -> str:
    """Dublikatų paieškai: mažosios raidės, suvienodinti tarpai."""
    normalized = _WHITESPACE_RE.sub(" ", issue_text(title, body).casefold()).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


def excluded_label(labels_json: str | None) -> str | None:
    """Pirmoji GitHub etiketė, rodanti, kad tai ne klaida, arba None."""
    try:
        labels = json.loads(labels_json or "[]")
    except ValueError:
        return None
    for label in labels if isinstance(labels, list) else []:
        if isinstance(label, str) and _is_non_bug_label(label):
            return label
    return None


def _is_non_bug_label(label: str) -> bool:
    text = label.casefold()
    for pattern in _BENIGN_LABEL_PATTERNS:
        text = pattern.sub(" ", text)
    return any(word in text for word in EXCLUDED_LABEL_KEYWORDS)


@dataclass(frozen=True)
class QualityResult:
    ok_ids: list[int]
    short_body_ids: list[int]
    duplicate_ids: list[int]
    excluded_label_ids: list[int]


def check_quality(conn: sqlite3.Connection) -> QualityResult:
    """Suskirsto importuotus issues į tinkamus ir atmestus (pagal priežastį).

    Iš kelių vienodų tekstų paliekamas tik pirmasis (mažiausias ID).
    """
    ok_ids: list[int] = []
    short_ids: list[int] = []
    duplicate_ids: list[int] = []
    label_ids: list[int] = []
    seen: set[str] = set()
    rows = conn.execute("SELECT id, title, body, labels_json FROM github_issues ORDER BY id")
    for issue_id, title, body, labels_json in rows:
        fingerprint = text_fingerprint(title, body)
        if fingerprint in seen:
            duplicate_ids.append(issue_id)
            continue
        seen.add(fingerprint)
        if excluded_label(labels_json):
            label_ids.append(issue_id)
        elif len((body or "").strip()) < MIN_BODY_CHARS:
            short_ids.append(issue_id)
        else:
            ok_ids.append(issue_id)
    return QualityResult(ok_ids, short_ids, duplicate_ids, label_ids)


def quality_report(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """Kiekvienos repozitorijos suvestinė: kiek įrašų, kiek atmesta ir kodėl."""
    quality = check_quality(conn)
    reasons = {issue_id: "ok" for issue_id in quality.ok_ids}
    reasons.update({issue_id: "short" for issue_id in quality.short_body_ids})
    reasons.update({issue_id: "duplicate" for issue_id in quality.duplicate_ids})
    reasons.update({issue_id: "excluded_label" for issue_id in quality.excluded_label_ids})

    report: dict[str, dict[str, object]] = {}
    rows = conn.execute(
        """
        SELECT g.id, g.repository_full_name, g.is_test_set, g.is_pilot_set,
               g.source_kind = 'augmentation' AS augmentation,
               g.category_label IS NOT NULL AND g.complexity_label IS NOT NULL
                   AND g.priority_label IS NOT NULL AS human_complete,
               EXISTS (SELECT 1 FROM ai_annotations a
                       WHERE a.github_issue_id = g.id AND a.status = 'ok') AS ai_labelled
        FROM github_issues g
        """
    )
    for issue_id, repository, is_test, is_pilot, augmentation, human_complete, ai_labelled in rows:
        item = report.setdefault(
            repository,
            {"repository": repository, "total": 0, "ok": 0, "short": 0, "duplicate": 0,
             "excluded_label": 0, "augmentation": 0, "pilot_set": 0, "test_set": 0,
             "human_complete": 0, "ai_labelled": 0},
        )
        item["total"] += 1
        item[reasons[issue_id]] += 1
        item["augmentation"] += augmentation
        item["pilot_set"] += is_pilot
        item["test_set"] += is_test
        item["human_complete"] += human_complete
        item["ai_labelled"] += ai_labelled
    return sorted(report.values(), key=lambda item: item["repository"].casefold())


_SUBSET_CONDITIONS = {
    None: "1 = 1",
    "pilot": "g.is_pilot_set = 1",
    "test": "g.is_test_set = 1",
    "training": "g.is_pilot_set = 0 AND g.is_test_set = 0",
}


def select_for_ai_labelling(
    conn: sqlite3.Connection,
    model: str,
    prompt_version: str,
    limit: int,
    max_attempts: int,
    subset: str | None = None,
) -> list[sqlite3.Row]:
    """Kokybės patikrą praėję įrašai, dar neturintys sėkmingos šio modelio DI žymos.

    `subset`: None – visi, "pilot" / "test" – tik to rinkinio, "training" – be jų.
    Įrašai imami paeiliui iš skirtingų repozitorijų (round-robin), kad net maža
    imtis apimtų kelis projektus.
    """
    if subset not in _SUBSET_CONDITIONS:
        raise ValueError("neteisingas subset")
    ok_ids = check_quality(conn).ok_ids
    if not ok_ids or limit < 1:
        return []
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS quality_ok (id INTEGER PRIMARY KEY)")
    conn.execute("DELETE FROM quality_ok")
    conn.executemany("INSERT INTO quality_ok (id) VALUES (?)", [(i,) for i in ok_ids])
    return conn.execute(
        f"""
        SELECT * FROM (
            SELECT g.*, ROW_NUMBER() OVER (
                PARTITION BY g.repository_full_name ORDER BY g.id) AS repo_position
            FROM github_issues g
            JOIN quality_ok q ON q.id = g.id
            LEFT JOIN ai_annotations a
                ON a.github_issue_id = g.id AND a.model = ? AND a.prompt_version = ?
            WHERE (a.id IS NULL OR (a.status = 'invalid' AND a.attempts < ?))
              AND {_SUBSET_CONDITIONS[subset]}
        )
        ORDER BY repo_position, repository_full_name, id
        LIMIT ?
        """,
        (model, prompt_version, max_attempts, limit),
    ).fetchall()


def _stratified_sample(by_repository: dict[str, list[int]], count: int, rng: random.Random) -> list[int]:
    """Proporcinga atranka pagal repozitorijas (didžiausios liekanos metodas)."""
    total = sum(len(ids) for ids in by_repository.values())
    count = min(count, total)
    if count <= 0:
        return []
    names = sorted(by_repository)
    exact = {name: count * len(by_repository[name]) / total for name in names}
    quota = {name: int(exact[name]) for name in names}
    remainder = count - sum(quota.values())
    for name in sorted(names, key=lambda n: (-(exact[n] - quota[n]), n))[:remainder]:
        quota[name] += 1
    chosen: list[int] = []
    for name in names:
        chosen += rng.sample(sorted(by_repository[name]), quota[name])
    return chosen


def _select_evaluation_set(
    conn: sqlite3.Connection, column: str, other_column: str, size: int, seed: int
) -> int:
    """Papildo rinkinį iki `size` įrašų; grąžina naujai pridėtų skaičių.

    Imami tik kokybiški pagrindinio rinkimo (ne papildymo) įrašai, nepriklausantys kitam
    rinkiniui; atranka atsitiktinė, su seed ir proporcinga pagal repozitorijas.
    """
    ok_ids = set(check_quality(conn).ok_ids)
    current = conn.execute(f"SELECT COUNT(*) FROM github_issues WHERE {column} = 1").fetchone()[0]
    needed = max(0, size - current)
    by_repository: dict[str, list[int]] = defaultdict(list)
    rows = conn.execute(
        f"SELECT id, repository_full_name FROM github_issues "
        f"WHERE {column} = 0 AND {other_column} = 0 AND source_kind = 'base'"
    )
    for issue_id, repository in rows:
        if issue_id in ok_ids:
            by_repository[repository].append(issue_id)
    chosen = _stratified_sample(by_repository, needed, random.Random(seed))
    with conn:
        conn.executemany(f"UPDATE github_issues SET {column} = 1 WHERE id = ?", [(i,) for i in chosen])
    return len(chosen)


def select_test_set(conn: sqlite3.Connection, size: int, seed: int) -> int:
    """Galutinis nepriklausomas žmogaus testavimo rinkinys (niekada nenaudojamas mokymui)."""
    return _select_evaluation_set(conn, "is_test_set", "is_pilot_set", size, seed)


def select_pilot_set(conn: sqlite3.Connection, size: int, seed: int) -> int:
    """Bandomasis DI kokybės ir kainos rinkinys (nenaudojamas galutiniam vertinimui)."""
    return _select_evaluation_set(conn, "is_pilot_set", "is_test_set", size, seed + 1)
