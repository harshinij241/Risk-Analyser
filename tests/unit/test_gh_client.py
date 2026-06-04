import pytest
import responses as rsps
from github_pipeline.client import GitHubClient, RepoVisibility


BASE = "https://api.github.com"


@rsps.activate
def test_validate_token_raises_on_401(fake_token):
    rsps.add(rsps.GET, f"{BASE}/user", status=401,
            json={"message": "Bad credentials"})
    client = GitHubClient(token=fake_token)
    with pytest.raises(PermissionError, match="invalid or expired"):
        client.validate_token(RepoVisibility.PUBLIC)


@rsps.activate
def test_validate_token_raises_on_missing_scope(fake_token):
    rsps.add(rsps.GET, f"{BASE}/user", status=200,
            json={"login": "alice"},
            headers={"X-OAuth-Scopes": "gist, notifications"})
    client = GitHubClient(token=fake_token)
    with pytest.raises(PermissionError, match="missing required scope"):
        client.validate_token(RepoVisibility.PUBLIC)


@rsps.activate
def test_validate_token_passes_with_correct_scope(fake_token):
    rsps.add(rsps.GET, f"{BASE}/user", status=200,
            json={"login": "alice"},
            headers={
                "X-OAuth-Scopes": "public_repo",
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": "9999999999"
            })
    client = GitHubClient(token=fake_token)
    client.validate_token(RepoVisibility.PUBLIC)  # should not raise


@rsps.activate
def test_get_returns_none_on_404(github_client):
    rsps.add(rsps.GET, f"{BASE}/repos/owner/repo",
            status=404, json={"message": "Not Found"})
    data, headers = github_client.get("/repos/owner/repo")
    assert data is None


@rsps.activate
def test_get_returns_none_on_304(github_client):
    rsps.add(rsps.GET, f"{BASE}/repos/owner/repo", status=304)
    data, headers = github_client.get(
        "/repos/owner/repo", etag="abc123"
    )
    assert data is None


@rsps.activate
def test_paginate_follows_link_header(github_client):
    page1_url = f"{BASE}/repos/owner/repo/commits"
    page2_url = f"{BASE}/repos/owner/repo/commits?page=2"

    rsps.add(rsps.GET, page1_url,
            json=[{"sha": "aaa"}],
            headers={"Link": f'<{page2_url}>; rel="next"'},
            status=200)
    rsps.add(rsps.GET, page2_url,
            json=[{"sha": "bbb"}],
            headers={},
            status=200)

    results = github_client.paginate("/repos/owner/repo/commits")
    assert len(results) == 2
    assert results[0]["sha"] == "aaa"
    assert results[1]["sha"] == "bbb"


@rsps.activate
def test_update_rate_limit_from_headers(github_client):
    rsps.add(rsps.GET, f"{BASE}/repos/owner/repo",
            json={"default_branch": "main"},
            headers={
                "X-RateLimit-Remaining": "42",
                "X-RateLimit-Reset": "1700000000"
            },
            status=200)
    github_client.get("/repos/owner/repo")
    assert github_client._rate.remaining == 42