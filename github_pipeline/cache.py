import json
import os
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from knowledge_risk.models import FileCommit

logger = logging.getLogger(__name__)


class CacheStore:
    """
    Persists per-file commit history between runs.
    Tracks last-seen commit SHA per file so we only
    fetch new commits on incremental runs.

    Storage format: one JSON file per repo in cache_dir.
    Key: file_path
    Value: {last_sha, last_fetched, commits: [...]}
    """

    def __init__(self, cache_dir: str = ".knowledge_risk_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, owner: str, repo: str) -> Path:
        key = hashlib.md5(f"{owner}/{repo}".encode()).hexdigest()[:8]
        return self.cache_dir / f"{owner}_{repo}_{key}.json"

    def load(self, owner: str, repo: str) -> dict:
        path = self._cache_path(owner, repo)
        if path.exists():
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                logger.warning(
                    f"Cache corrupted for {owner}/{repo}. "
                    "Starting fresh."
                )
        return {}

    def save(self, owner: str, repo: str, data: dict) -> None:
        path = self._cache_path(owner, repo)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def get_last_sha(self,
                     cache: dict,
                     file_path: str) -> Optional[str]:
        return cache.get(file_path, {}).get("last_sha")

    def get_cached_commits(self,
                           cache: dict,
                           file_path: str) -> list[dict]:
        return cache.get(file_path, {}).get("commits", [])

    def update_file(self,
                    cache: dict,
                    file_path: str,
                    new_commits: list[dict],
                    last_sha: str) -> dict:
        """
        Merges new commits with cached ones.
        New commits are prepended (most recent first).
        """
        existing = self.get_cached_commits(cache, file_path)

        # Deduplicate by SHA
        existing_shas = {c["sha"] for c in existing}
        truly_new = [
            c for c in new_commits
            if c["sha"] not in existing_shas
        ]

        merged = truly_new + existing

        cache[file_path] = {
            "last_sha":     last_sha,
            "last_fetched": datetime.now().isoformat(),
            "commits":      merged
        }
        return cache

    def serialize_commits(self,
                          commits: list[FileCommit]) -> list[dict]:
        """Convert FileCommit objects to JSON-serializable dicts."""
        return [
            {
                "sha":           c.commit_hash,
                "author":        c.author,
                "timestamp":     c.timestamp.isoformat(),
                "lines_added":   c.lines_added,
                "lines_deleted": c.lines_deleted,
                "message":       c.message
            }
            for c in commits
        ]

    def deserialize_commits(self,
                            file_path: str,
                            raw: list[dict]) -> list[FileCommit]:
        """Rebuild FileCommit objects from cached JSON."""
        commits = []
        for c in raw:
            try:
                commits.append(FileCommit(
                    file_path    = file_path,
                    author       = c["author"],
                    timestamp    = datetime.fromisoformat(c["timestamp"]),
                    lines_added  = c.get("lines_added", 0),
                    lines_deleted= c.get("lines_deleted", 0),
                    commit_hash  = c.get("sha", ""),
                    message      = c.get("message", "")
                ))
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed cache entry: {e}")
        return commits