"""GitHub issues kokybės patikra ir atranka DI žymėjimui bei mokymui.

Taisyklės paprastos ir dokumentuotos (README, docs/DATA_LABELING.md):
- per trumpas aprašymas – iš jo neįmanoma nustatyti klaidos pobūdžio;
- pasikartojantis tekstas – dublikatai iškreiptų mokymą ir vertinimą;
- pull request įrašai importo metu jau atmesti.
"""

import hashlib
import random
import re
import sqlite3
from dataclasses import dataclass

MIN_BODY_CHARS = 30

_WHITESPACE_RE = re.compile(r"\s+")


def issue_text(title: str, body: str | None) -> str:
    """Deterministinis modelio įvesties tekstas: pavadinimas + aprašymas."""
    return f"{title.strip()}\n\n{(body or '').strip()}".strip()


def text_fingerprint(title: str, body: str | None) -> str:
    """Dublikatų paieškai: mažosios raidės, suvienodinti tarpai."""
    normalized = _WHITESPACE_RE.sub(" ", issue_text(title, body).casefold()).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


@dataclass(frozen=True)
class QualityResult:
    ok_ids: list[int]
    short_body_ids: list[int]
    duplicate_ids: list[int]


def check_quality(conn: sqlite3.Connection) -> QualityResult:
    """Suskirsto importuotus issues į tinkamus ir atmestus (pagal priežastį).

    Iš kelių vienodų tekstų paliekamas tik pirmasis (mažiausias ID).
    """
    ok_ids: list[int] = []
    short_ids: list[int] = []
    duplicate_ids: list[int] = []
    seen: set[str] = set()
    rows = conn.execute("SELECT id, title, body FROM github_issues ORDER BY id")
    for issue_id, title, body in rows:
        fingerprint = text_fingerprint(title, body)
        if fingerprint in seen:
            duplicate_ids.append(issue_id)
            continue
        seen.add(fingerprint)
        if len((body or "").strip()) < MIN_BODY_CHARS:
            short_ids.append(issue_id)
        else:
            ok_ids.append(issue_id)
    return QualityResult(ok_ids, short_ids, duplicate_ids)


def quality_report(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """Kiekvienos repozitorijos suvestinė: kiek įrašų, kiek atmesta ir kodėl."""
    quality = check_quality(conn)
    reasons = {issue_id: "ok" for issue_id in quality.ok_ids}
    reasons.update({issue_id: "short" for issue_id in quality.short_body_ids})
    reasons.update({issue_id: "duplicate" for issue_id in quality.duplicate_ids})

    report: dict[str, dict[str, object]] = {}
    rows = conn.execute(
        """
        SELECT g.id, g.repository_full_name, g.is_test_set,
               g.category_label IS NOT NULL AND g.complexity_label IS NOT NULL
                   AND g.priority_label IS NOT NULL AS human_complete,
               EXISTS (SELECT 1 FROM ai_annotations a
                       WHERE a.github_issue_id = g.id AND a.status = 'ok') AS ai_labelled
        FROM github_issues g
        """
    )
    for issue_id, repository, is_test, human_complete, ai_labelled in rows:
        item = report.setdefault(
            repository,
            {"repository": repository, "total": 0, "ok": 0, "short": 0, "duplicate": 0,
             "test_set": 0, "human_complete": 0, "ai_labelled": 0},
        )
        item["total"] += 1
        item[reasons[issue_id]] += 1
        item["test_set"] += is_test
        item["human_complete"] += human_complete
        item["ai_labelled"] += ai_labelled
    return sorted(report.values(), key=lambda item: item["repository"].casefold())


def select_for_ai_labelling(
    conn: sqlite3.Connection,
    model: str,
    prompt_version: str,
    limit: int,
    max_attempts: int,
) -> list[sqlite3.Row]:
    """Kokybės patikrą praėję įrašai, dar neturintys sėkmingos šio modelio DI žymos.

    Įrašai imami paeiliui iš skirtingų repozitorijų (round-robin), kad net maža
    bandomoji imtis apimtų kelis projektus.
    """
    ok_ids = check_quality(conn).ok_ids
    if not ok_ids or limit < 1:
        return []
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS quality_ok (id INTEGER PRIMARY KEY)")
    conn.execute("DELETE FROM quality_ok")
    conn.executemany("INSERT INTO quality_ok (id) VALUES (?)", [(i,) for i in ok_ids])
    return conn.execute(
        """
        SELECT * FROM (
            SELECT g.*, ROW_NUMBER() OVER (
                PARTITION BY g.repository_full_name ORDER BY g.id) AS repo_position
            FROM github_issues g
            JOIN quality_ok q ON q.id = g.id
            LEFT JOIN ai_annotations a
                ON a.github_issue_id = g.id AND a.model = ? AND a.prompt_version = ?
            WHERE a.id IS NULL OR (a.status = 'invalid' AND a.attempts < ?)
        )
        ORDER BY repo_position, repository_full_name, id
        LIMIT ?
        """,
        (model, prompt_version, max_attempts, limit),
    ).fetchall()


def select_test_set(conn: sqlite3.Connection, size: int, seed: int) -> int:
    """Atsitiktinai pažymi `size` kokybiškų įrašų žmogaus testavimo rinkiniui.

    Jau pažymėti įrašai paliekami; grąžina naujai pridėtų skaičių. Testavimo
    rinkinio įrašai niekada nenaudojami mokymui.
    """
    ok_ids = set(check_quality(conn).ok_ids)
    current = {row[0] for row in conn.execute("SELECT id FROM github_issues WHERE is_test_set = 1")}
    candidates = sorted(ok_ids - current)
    needed = max(0, size - len(current))
    chosen = random.Random(seed).sample(candidates, min(needed, len(candidates)))
    with conn:
        conn.executemany("UPDATE github_issues SET is_test_set = 1 WHERE id = ?", [(i,) for i in chosen])
    return len(chosen)
