import httpx
import pytest

from app.services import github_client
from app.services.github_client import (
    GitHubError,
    InvalidRepositoryError,
    fetch_issues,
    parse_repository,
)


def make_issue(number: int, pull_request: bool = False) -> dict:
    issue = {
        "number": number,
        "title": f"Issue {number}",
        "state": "open",
        "html_url": f"https://github.com/o/r/issues/{number}",
        "body": "text",
        "labels": [],
    }
    if pull_request:
        issue["pull_request"] = {"url": "https://api.github.com/repos/o/r/pulls/1"}
    return issue


def transport_for(pages: dict[int, list], requests: list | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json=pages.get(page, []))

    return httpx.MockTransport(handler)


def status_transport(status: int, headers: dict | None = None) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, headers=headers))


@pytest.mark.parametrize(
    "value",
    [
        "owner/repo",
        " owner/repo ",
        "https://github.com/owner/repo",
        "https://github.com/owner/repo/",
        "https://GitHub.com/owner/my.repo-1",
    ],
)
def test_parse_repository_accepts_valid_values(value: str) -> None:
    assert parse_repository(value).count("/") == 1


@pytest.mark.parametrize(
    "value",
    [
        "owner/repo.git",
        "https://github.com/owner/repo.git",
        "https://github.com/owner/repo.GIT/",
    ],
)
def test_parse_repository_strips_git_suffix(value: str) -> None:
    assert parse_repository(value) == "owner/repo"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "owner",
        "a/b/c",
        "-owner/repo",
        "owner/..",
        "owner/.git",
        "owner/re po",
        "owner/repo?x=1",
        "http://github.com/owner/repo",
        "https://evil.example/owner/repo",
        "https://github.com.evil.example/owner/repo",
        "https://user@github.com/owner/repo",
        "https://github.com:8443/owner/repo",
        "https://github.com/owner/repo/issues",
        "https://github.com/owner/repo?tab=x",
        "https://api.github.com/repos/owner/repo",
        "file:///etc/passwd",
        "git@github.com:owner/repo",
    ],
)
def test_parse_repository_rejects_invalid_values_and_foreign_hosts(value: str) -> None:
    with pytest.raises(InvalidRepositoryError):
        parse_repository(value)


def test_fetch_issues_follows_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_client, "PER_PAGE", 2)
    pages = {1: [make_issue(1), make_issue(2)], 2: [make_issue(3), make_issue(4)], 3: [make_issue(5)]}
    requests: list[httpx.Request] = []

    result = fetch_issues("o/r", 100, transport=transport_for(pages, requests))

    assert [issue["number"] for issue in result.issues] == [1, 2, 3, 4, 5]
    assert [r.url.params["page"] for r in requests] == ["1", "2", "3"]


def test_fetch_issues_respects_limit_and_stops_early(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_client, "PER_PAGE", 2)
    pages = {1: [make_issue(1), make_issue(2)], 2: [make_issue(3), make_issue(4)]}
    requests: list[httpx.Request] = []

    result = fetch_issues("o/r", 3, transport=transport_for(pages, requests))

    assert len(result.issues) == 3
    assert len(requests) == 2


def test_fetch_issues_skips_pull_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_client, "PER_PAGE", 3)
    pages = {1: [make_issue(1), make_issue(2, pull_request=True), make_issue(3)]}

    result = fetch_issues("o/r", 10, transport=transport_for(pages))

    assert [issue["number"] for issue in result.issues] == [1, 3]
    assert result.skipped_pull_requests == 1


def test_fetch_issues_only_calls_fixed_github_api_host() -> None:
    requests: list[httpx.Request] = []

    fetch_issues("https://github.com/Owner/Repo", 5, transport=transport_for({1: []}, requests))

    assert [(r.url.host, r.url.path, r.method) for r in requests] == [
        ("api.github.com", "/repos/Owner/Repo/issues", "GET")
    ]


def test_fetch_issues_rejects_foreign_host_without_any_request() -> None:
    requests: list[httpx.Request] = []

    with pytest.raises(InvalidRepositoryError):
        fetch_issues("https://evil.example/o/r", 5, transport=transport_for({}, requests))

    assert requests == []


def test_token_is_sent_only_when_provided() -> None:
    requests: list[httpx.Request] = []

    fetch_issues("o/r", 1, transport=transport_for({1: []}, requests))
    fetch_issues("o/r", 1, token="secret-token", transport=transport_for({1: []}, requests))

    assert "authorization" not in requests[0].headers
    assert requests[1].headers["authorization"] == "Bearer secret-token"


def test_not_found_error() -> None:
    with pytest.raises(GitHubError) as exc_info:
        fetch_issues("o/r", 1, transport=status_transport(404))
    assert exc_info.value.status_code == 404


@pytest.mark.parametrize(
    ("status", "headers"),
    [(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1893456000"}), (429, {})],
)
def test_rate_limit_error(status: int, headers: dict) -> None:
    with pytest.raises(GitHubError) as exc_info:
        fetch_issues("o/r", 1, token="secret-token", transport=status_transport(status, headers))
    assert exc_info.value.status_code == 429
    assert "limitas" in exc_info.value.message
    assert "secret-token" not in exc_info.value.message


@pytest.mark.parametrize("status", [401, 403, 410, 500])
def test_other_http_errors(status: int) -> None:
    with pytest.raises(GitHubError) as exc_info:
        fetch_issues("o/r", 1, transport=status_transport(status))
    assert exc_info.value.status_code == 502


def test_network_error_and_timeout() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(GitHubError) as connect_error:
        fetch_issues("o/r", 1, transport=httpx.MockTransport(refuse))
    with pytest.raises(GitHubError) as timeout_error:
        fetch_issues("o/r", 1, transport=httpx.MockTransport(slow))

    assert connect_error.value.status_code == 502
    assert timeout_error.value.status_code == 504


def test_unexpected_response_body() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"message": "x"}))
    with pytest.raises(GitHubError):
        fetch_issues("o/r", 1, transport=transport)
