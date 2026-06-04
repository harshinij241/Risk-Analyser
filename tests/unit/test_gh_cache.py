import pytest
import json
from datetime import datetime
from knowledge_risk.models import FileCommit
from github_pipeline.cache import CacheStore


@pytest.fixture
def cache(tmp_path):
    return CacheStore(cache_dir=str(tmp_path / "cache"))


@pytest.fixture
def sample_commit():
    return FileCommit(
        file_path    = "src/foo.py",
        author       = "alice",
        timestamp    = datetime(2024, 6, 1, 10, 0, 0),
        lines_added  = 50,
        lines_deleted= 10,
        commit_hash  = "abc123",
        message      = "fix payment logic"
    )


def test_load_returns_empty_for_new_repo(cache):
    result = cache.load("owner", "newrepo")
    assert result == {}


def test_save_and_load_roundtrip(cache, sample_commit):
    data = {}
    serialized = cache.serialize_commits([sample_commit])
    data = cache.update_file(data, "src/foo.py",
                             serialized, "abc123")
    cache.save("owner", "repo", data)

    loaded = cache.load("owner", "repo")
    assert "src/foo.py" in loaded
    assert loaded["src/foo.py"]["last_sha"] == "abc123"


def test_load_returns_empty_on_corrupted_file(
        cache, tmp_path):
    # Write invalid JSON to cache file
    path = list((tmp_path / "cache").glob("*.json"))
    cache.save("owner", "repo", {"key": "value"})
    cache_files = list((tmp_path / "cache").glob("*.json"))
    if cache_files:
        cache_files[0].write_text("not valid json {{{")
    result = cache.load("owner", "repo")
    assert result == {}


def test_get_last_sha_returns_none_for_unseen(cache):
    assert cache.get_last_sha({}, "src/foo.py") is None


def test_get_last_sha_returns_correct_sha(cache, sample_commit):
    data = {}
    serialized = cache.serialize_commits([sample_commit])
    data = cache.update_file(data, "src/foo.py",
                             serialized, "abc123")
    assert cache.get_last_sha(data, "src/foo.py") == "abc123"


def test_update_file_deduplicates_by_sha(cache, sample_commit):
    data = {}
    serialized = cache.serialize_commits([sample_commit])
    data = cache.update_file(data, "src/foo.py",
                             serialized, "abc123")
    # Add same commit again
    data = cache.update_file(data, "src/foo.py",
                             serialized, "abc123")
    commits = cache.get_cached_commits(data, "src/foo.py")
    shas = [c["sha"] for c in commits]
    assert len(shas) == len(set(shas))


def test_deserialize_skips_malformed_entries(cache):
    raw = [
        {
            "sha": "abc",
            "author": "alice",
            "timestamp": "2024-06-01T10:00:00",
            "lines_added": 10,
            "lines_deleted": 5,
            "message": "fix"
        },
        {
            "broken": True   # missing required fields
        }
    ]
    commits = cache.deserialize_commits("src/foo.py", raw)
    assert len(commits) == 1
    assert commits[0].author == "alice"