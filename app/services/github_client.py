"""Tik skaitymo GitHub REST klientas viešų repozitorijų issues importui."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import httpx

# Užklausos visada siunčiamos į šį fiksuotą hostą; naudotojo tekstas niekada
# nevirsta pilnu URL (apsauga nuo SSRF).
API_BASE_URL = "https://api.github.com"
PER_PAGE = 100
MAX_PAGES = 10
REQUEST_TIMEOUT = 10.0

# GitHub pervadintas ar perkeltas repozitorijas nukreipia (pvz. 301 į
# /repositories/<id>/issues). Peradresavimai vykdomi rankiniu būdu, kad kiekvienas
# `Location` būtų patikrintas prieš siunčiant užklausą.
REDIRECT_STATUSES = frozenset({301, 302, 307, 308})
MAX_REDIRECTS = 3
_REDIRECT_HOST = "api.github.com"
_REDIRECT_PATH_PREFIXES = ("/repos/", "/repositories/")

_OWNER_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
_REPO_RE = re.compile(r"[A-Za-z0-9._-]{1,100}")
_LABELS_RE = re.compile(r"[^\x00-\x1f]{1,200}")
_INVALID_REPOSITORY_MESSAGE = (
    "Neteisingas repozitorijos formatas. Naudokite owner/repo arba "
    "https://github.com/owner/repo."
)


class InvalidRepositoryError(ValueError):
    pass


class GitHubError(Exception):
    """GitHub užklausos klaida su naudotojui rodomu pranešimu."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class FetchedIssues:
    issues: list[object]
    skipped_pull_requests: int


def parse_repository(value: str) -> str:
    """Grąžina normalizuotą `owner/repo` arba meta InvalidRepositoryError."""
    text = value.strip()
    if "://" in text:
        try:
            parts = urlsplit(text)
        except ValueError:
            raise InvalidRepositoryError(_INVALID_REPOSITORY_MESSAGE) from None
        # netloc palyginimas atmeta ir naudotojo vardą, ir portą.
        if (
            parts.scheme != "https"
            or parts.netloc.lower() != "github.com"
            or parts.query
            or parts.fragment
        ):
            raise InvalidRepositoryError(_INVALID_REPOSITORY_MESSAGE)
        text = parts.path.strip("/")

    segments = text.split("/")
    if len(segments) != 2:
        raise InvalidRepositoryError(_INVALID_REPOSITORY_MESSAGE)
    owner, repo = segments
    # GitHub nuorodos dažnai kopijuojamos su `.git` galūne (clone URL).
    if repo.lower().endswith(".git"):
        repo = repo[: -len(".git")]
    if (
        not _OWNER_RE.fullmatch(owner)
        or not _REPO_RE.fullmatch(repo)
        or repo in {".", ".."}
    ):
        raise InvalidRepositoryError(_INVALID_REPOSITORY_MESSAGE)
    return f"{owner}/{repo}"


def fetch_issues(
    repository: str,
    limit: int,
    token: str | None = None,
    transport: httpx.BaseTransport | None = None,
    labels: str | None = None,
) -> FetchedIssues:
    """Paima iki `limit` issues (be pull request) iš viešos repozitorijos.

    `labels` – neprivalomas GitHub etikečių filtras (pvz. "bug"), perduodamas
    kaip užklausos parametras; naudojamas tik masinio importo CLI.
    """
    if limit < 1:
        raise ValueError("limit turi būti teigiamas")
    if labels is not None and not _LABELS_RE.fullmatch(labels):
        raise ValueError("neteisingas etikečių filtras")
    full_name = parse_repository(repository)  # pakartotinis patikrinimas

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "bakalauras-issue-importer",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{API_BASE_URL}/repos/{full_name}/issues"
    issues: list[object] = []
    skipped = 0
    with httpx.Client(
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        transport=transport,
        follow_redirects=False,
    ) as client:
        for page in range(1, MAX_PAGES + 1):
            # url atnaujinamas po peradresavimo, kad kiti puslapiai nebūtų nukreipiami iš naujo.
            items, url = _get_page(client, url, page, labels)
            for item in items:
                if isinstance(item, dict) and "pull_request" in item:
                    skipped += 1
                    continue
                issues.append(item)
                if len(issues) >= limit:
                    return FetchedIssues(issues, skipped)
            if len(items) < PER_PAGE:
                break
    return FetchedIssues(issues, skipped)


def _get_page(
    client: httpx.Client, url: str, page: int, labels: str | None = None
) -> tuple[list[object], str]:
    params: dict[str, object] = {
        "state": "all",
        "sort": "created",
        "direction": "desc",
        "per_page": PER_PAGE,
        "page": page,
    }
    if labels:
        params["labels"] = labels
    try:
        response, url = _get_following_redirects(client, url, params)
    except httpx.TimeoutException:
        raise GitHubError("GitHub API neatsakė laiku. Bandykite vėliau.", 504) from None
    except httpx.RequestError:
        raise GitHubError("Nepavyko prisijungti prie GitHub API.", 502) from None

    _raise_for_status(response)
    try:
        data = response.json()
    except ValueError:
        data = None
    if not isinstance(data, list):
        raise GitHubError("GitHub API grąžino netikėtą atsakymą.", 502)
    return data, url


def _get_following_redirects(
    client: httpx.Client, url: str, params: dict[str, object]
) -> tuple[httpx.Response, str]:
    """GET su ribotu, patikrintu peradresavimų sekimu.

    Grąžina atsakymą ir galutinį URL be užklausos eilutės (kitiems puslapiams).
    """
    query: dict[str, object] | None = params
    for _ in range(MAX_REDIRECTS + 1):
        response = client.get(url, params=query)
        if response.status_code not in REDIRECT_STATUSES:
            return response, urlsplit(url)._replace(query="", fragment="").geturl()
        url = _redirect_target(url, response.headers.get("location"))
        # Jei GitHub `Location` jau turi užklausos eilutę, jos nekeičiame.
        query = None if urlsplit(url).query else params
    raise GitHubError("GitHub API grąžino per daug peradresavimų.", 502)


def _redirect_target(current_url: str, location: str | None) -> str:
    """Patikrina `Location`: tik HTTPS, tik api.github.com, be naudotojo vardo ir porto."""
    error = GitHubError("GitHub API grąžino neleistiną peradresavimą.", 502)
    if not location:
        raise error
    try:
        target = urljoin(current_url, location)
        parts = urlsplit(target)
        port = parts.port
    except ValueError:
        raise error from None
    if (
        parts.scheme != "https"
        or parts.hostname != _REDIRECT_HOST
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
        or not parts.path.startswith(_REDIRECT_PATH_PREFIXES)
    ):
        raise error
    return target


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status == 200:
        return
    if status == 404:
        raise GitHubError("Repozitorija nerasta arba nėra vieša.", 404)
    if status == 429 or (
        status == 403 and response.headers.get("x-ratelimit-remaining") == "0"
    ):
        raise GitHubError(_rate_limit_message(response), 429)
    if status == 410:
        raise GitHubError("Šioje repozitorijoje issues yra išjungti.", 502)
    raise GitHubError(f"GitHub API grąžino klaidą (HTTP {status}).", 502)


def _rate_limit_message(response: httpx.Response) -> str:
    message = "Pasiektas GitHub API užklausų limitas."
    try:
        reset = datetime.fromtimestamp(
            int(response.headers["x-ratelimit-reset"]), timezone.utc
        )
    except (KeyError, ValueError, OverflowError, OSError):
        return f"{message} Bandykite vėliau arba nustatykite GITHUB_TOKEN."
    return (
        f"{message} Limitas atsinaujins apie {reset:%Y-%m-%d %H:%M} UTC; "
        "arba nustatykite GITHUB_TOKEN."
    )
