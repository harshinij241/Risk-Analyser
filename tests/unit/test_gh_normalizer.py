import pytest
from datetime import datetime
from github_pipeline.normalizer import CommitNormalizer


@pytest.fixture
def normalizer():
    return CommitNormalizer()


def test_from_rest_commit_prefers_login(normalizer):
    commit = {
        "sha": "abc123",
        "author": {"login": "alice"},
        "commit": {
            "author": {
                "name": "Alice Smith",
                "email": "alice@company.com",
                "date": "2024-06-01T10:00:00Z"
            },
            "message": "fix payment logic"
        }
    }
    result = normalizer.from_rest_commit("src/foo.py", commit, {
        "additions": 10, "deletions": 5
    })
    assert result.author == "alice"
    assert result.lines_added == 10
    assert result.lines_deleted == 5


def test_from_rest_commit_falls_back_to_email(normalizer):
    commit = {
        "sha": "abc123",
        "author": {},   # no login
        "commit": {
            "author": {
                "name": "Alice",
                "email": "alice@company.com",
                "date": "2024-06-01T10:00:00Z"
            },
            "message": "fix"
        }
    }
    result = normalizer.from_rest_commit("src/foo.py", commit, {})
    assert result.author == "alice@company.com"


def test_from_rest_commit_handles_bad_date(normalizer):
    commit = {
        "sha": "abc123",
        "author": {"login": "alice"},
        "commit": {
            "author": {
                "name": "Alice",
                "email": "alice@co.com",
                "date": "not-a-date"
            },
            "message": "fix"
        }
    }
    result = normalizer.from_rest_commit("src/foo.py", commit, {})
    # Should not raise — falls back to datetime.now()
    assert isinstance(result.timestamp, datetime)


def test_from_graphql_commit_sets_lines_to_zero(normalizer):
    node = {
        "oid": "def456",
        "message": "refactor auth",
        "committedDate": "2024-05-01T08:00:00Z",
        "author": {
            "email": "bob@company.com",
            "name": "Bob",
            "user": {"login": "bob"}
        }
    }
    result = normalizer.from_graphql_commit("src/auth.py", node)
    assert result.lines_added == 0
    assert result.lines_deleted == 0
    assert result.author == "bob"


def test_is_bot_email_detects_noreply(normalizer):
    assert normalizer._is_bot_email("41898282+bot@noreply@github.com")


def test_is_bot_email_passes_human(normalizer):
    assert not normalizer._is_bot_email("alice@company.com")