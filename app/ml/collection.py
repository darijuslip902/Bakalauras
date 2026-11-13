"""GitHub issues rinkimas pagal šaltinių failą (`tools/sources.json`).

Užklausos siunčiamos tik į fiksuotą `api.github.com` per esamą tik skaitymo klientą;
pagal nutylėjimą be autentifikacijos (viešų issues skaitymui jos nereikia).
"""

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.services.annotation_service import LABEL_FIELDS
from app.services.github_client import (
    MAX_PAGES,
    PER_PAGE,
    GitHubError,
    InvalidRepositoryError,
    count_issues,
    fetch_issues,
    parse_repository,
)
from app.services.import_service import run_import

MAX_LIMIT_PER_SOURCE = MAX_PAGES * PER_PAGE  # 3000: GitHub klientas skaito iki 30 puslapių po 100


class SourcesError(ValueError):
    """Neteisingas šaltinių failas."""


@dataclass(frozen=True)
class Source:
    repository: str
    label: str | None
    limit: int


@dataclass(frozen=True)
class Sources:
    base: list[Source]
    augment: dict[tuple[str, str], list[Source]]  # (laukas, klasė) -> šaltiniai


def _parse_source(item: object, where: str) -> Source:
    if not isinstance(item, dict) or not isinstance(item.get("repo"), str):
        raise SourcesError(f"{where}: reikia objekto su 'repo'")
    try:
        repository = parse_repository(item["repo"])
    except InvalidRepositoryError as exc:
        raise SourcesError(f"{where}: {exc}") from None
    label = item.get("label")
    if label is not None and (not isinstance(label, str) or not label.strip()):
        raise SourcesError(f"{where}: 'label' turi būti netuščias tekstas")
    limit = item.get("limit", 100)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT_PER_SOURCE:
        raise SourcesError(f"{where}: 'limit' turi būti nuo 1 iki {MAX_LIMIT_PER_SOURCE}")
    return Source(repository, label.strip() if label else None, limit)


def load_sources(path: Path) -> Sources:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SourcesError(f"Nepavyko perskaityti {path}: {exc}") from None
    if not isinstance(data, dict) or not isinstance(data.get("base"), list):
        raise SourcesError("Šaltinių faile turi būti sąrašas 'base'")
    base = [_parse_source(item, f"base[{index}]") for index, item in enumerate(data["base"])]
    augment: dict[tuple[str, str], list[Source]] = {}
    for key, items in (data.get("augment") or {}).items():
        field, _, value = key.partition(":")
        if field not in LABEL_FIELDS or value not in LABEL_FIELDS[field]:
            raise SourcesError(f"augment: nežinoma klasė '{key}' (formatas laukas:reikšmė)")
        if not isinstance(items, list):
            raise SourcesError(f"augment['{key}']: reikia sąrašo")
        augment[(field, value)] = [_parse_source(item, f"augment['{key}']") for item in items]
    return Sources(base, augment)


def check_sources(
    sources: list[Source],
    token: str | None = None,
    transport: httpx.BaseTransport | None = None,
    with_counts: bool = False,
    pause: Callable[[], None] | None = None,
) -> list[dict[str, object]]:
    """Nemokama patikra: po vieną užklausą kiekvienam šaltiniui – ar etiketė grąžina issues.

    `with_counts` papildomai paprašo bendro issues skaičiaus (Search API, `pause` kviečiamas
    tarp užklausų, kad nebūtų viršytas minutės limitas); skaičius pateikiamas pranešime.
    """
    results = []
    for index, source in enumerate(sources):
        try:
            found = len(fetch_issues(source.repository, 1, token, transport, source.label).issues)
            status = "ok" if found else "empty"
            message = "rasta issues" if found else "0 issues – patikrinkite etiketės pavadinimą"
            if with_counts and found:
                if pause is not None and index:
                    pause()
                total = count_issues(source.repository, source.label, token, transport)
                message = f"iš viso issues (be PR): {total}"
                if total < source.limit:
                    message += f" – mažiau nei limit {source.limit}"
        except (GitHubError, ValueError) as exc:
            status, message = "error", getattr(exc, "message", str(exc))
        results.append({"source": source, "status": status, "message": message})
        if status == "error" and "limitas" in message:
            break  # pasiektas GitHub užklausų limitas – toliau tikrinti beprasmiška
    return results


def _stored_issue_count(conn: sqlite3.Connection, source: Source) -> int:
    """Kiek šaltinio atitinkančių issues jau yra DB (repozitorija + etiketė, jei nurodyta)."""
    try:
        if source.label is None:
            row = conn.execute(
                "SELECT COUNT(*) FROM github_issues WHERE repository_full_name = ?",
                (source.repository,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM github_issues WHERE repository_full_name = ? AND EXISTS "
                "(SELECT 1 FROM json_each(labels_json) WHERE lower(value) = lower(?))",
                (source.repository, source.label),
            ).fetchone()
    except sqlite3.DatabaseError:
        return 0  # sugadintas labels_json ar nėra JSON funkcijų – tiesiog renkame iš naujo
    return int(row[0])


def is_source_completed(conn: sqlite3.Connection, source: Source) -> bool:
    """Ar šaltinis jau visiškai surinktas.

    Pirmiausia tikrinama išsaugota būsena (`collection_progress`): pakanka, jei anksčiau
    surinkta bent tiek, kiek prašoma dabar. Jei būsenos nėra (DB sukurta prieš šią funkciją),
    šaltinis laikomas surinktu, kai DB jau turi bent `limit` jį atitinkančių issues.
    """
    row = conn.execute(
        "SELECT completed_limit FROM collection_progress WHERE repository_full_name = ? AND label = ?",
        (source.repository, source.label or ""),
    ).fetchone()
    if row is not None:
        return row[0] >= source.limit
    return _stored_issue_count(conn, source) >= source.limit


def mark_source_completed(conn: sqlite3.Connection, source: Source) -> None:
    completed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        conn.execute(
            "INSERT INTO collection_progress (repository_full_name, label, completed_limit, completed_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT (repository_full_name, label) DO UPDATE SET "
            "completed_limit = MAX(completed_limit, excluded.completed_limit), "
            "completed_at = excluded.completed_at",
            (source.repository, source.label or "", source.limit, completed_at),
        )


def import_sources(
    conn: sqlite3.Connection,
    sources: list[Source],
    source_kind: str,
    token: str | None = None,
    transport: httpx.BaseTransport | None = None,
    progress: Callable[[str], None] = print,
    skip_completed: bool = True,
) -> dict[str, int]:
    """Importuoja šaltinius; klaida viename šaltinyje nestabdo kitų.

    Visiškai surinkti šaltiniai (žr. `is_source_completed`) praleidžiami, todėl po GitHub
    API limito paleidus iš naujo tęsiama nuo pirmo neužbaigto šaltinio. `skip_completed=False`
    surenka viską iš naujo.
    """
    totals = {"imported": 0, "updated": 0, "skipped_sources": 0, "failed_sources": 0}
    for source in sources:
        name = f"{source.repository} [{source.label or 'visos etiketės'}]"
        if skip_completed and is_source_completed(conn, source):
            totals["skipped_sources"] += 1
            progress(f"{name}: praleistas – jau surinktas")
            continue
        try:
            result = run_import(conn, source.repository, source.limit, token, transport, source.label, source_kind)
        except (GitHubError, ValueError) as exc:
            totals["failed_sources"] += 1
            progress(f"{name}: KLAIDA – {getattr(exc, 'message', exc)}")
            if "limitas" in str(getattr(exc, "message", "")):
                progress("GitHub užklausų limitas pasiektas – paleiskite tą pačią komandą vėliau: "
                         "baigti šaltiniai bus praleisti, tęsiama nuo šio.")
                break
            continue
        mark_source_completed(conn, source)  # tik po sėkmingo viso šaltinio importo
        totals["imported"] += result.imported
        totals["updated"] += result.updated
        progress(f"{name}: nauji {result.imported}, atnaujinti {result.updated}, "
                 f"apsaugoti (testo / pažymėti) {result.protected}, "
                 f"praleisti PR {result.skipped_pull_requests}, nepavyko {result.failed}")
    return totals
