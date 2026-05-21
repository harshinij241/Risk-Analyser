import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
from .client import GitHubClient, RepoVisibility
from .scanner import RepoScanner, ScanConfig
from .fetcher import CommitHistoryFetcher
from .normalizer import CommitNormalizer
from .cache import CacheStore
from knowledge_risk.models import FileCommit

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    owner:           str
    repo:            str
    token:           str
    visibility:      RepoVisibility = RepoVisibility.PUBLIC
    max_commits:     int            = 500
    max_files:       int            = 2000
    max_concurrency: int            = 5
    path_prefix:     Optional[str]  = None
    cache_dir:       str            = ".knowledge_risk_cache"
    use_cache:       bool           = True


def build_file_commit_map(config: PipelineConfig) -> dict[str, list[FileCommit]]:
    """
    Main entry point for the GitHub pipeline.
    Returns file_commit_map ready for knowledge_risk.run_pipeline().
    """

    # 1. Initialize components
    client = GitHubClient(
        token           = config.token,
        max_concurrency = config.max_concurrency
    )

    # 2. Validate token upfront — fail fast
    client.validate_token(config.visibility)

    scanner = RepoScanner(
        client = client,
        config = ScanConfig(
            path_prefix = config.path_prefix,
            max_files   = config.max_files
        )
    )

    fetcher = CommitHistoryFetcher(
        client      = client,
        normalizer  = CommitNormalizer(),
        max_commits = config.max_commits
    )

    cache = CacheStore(config.cache_dir) if config.use_cache else None

    # 3. Discover files
    logger.info(f"Scanning {config.owner}/{config.repo}...")
    files = scanner.scan(config.owner, config.repo)
    logger.info(f"Discovered {len(files)} files.")

    # 4. Load cache
    cached_data = {}
    if cache:
        cached_data = cache.load(config.owner, config.repo)
        logger.info(
            f"Cache loaded: {len(cached_data)} files previously fetched."
        )

    # 5. Fetch commit history per file
    file_commit_map: dict[str, list[FileCommit]] = {}

    for i, file_path in enumerate(files, 1):
        logger.info(f"[{i}/{len(files)}] Fetching: {file_path}")

        last_sha = (
            cache.get_last_sha(cached_data, file_path)
            if cache else None
        )

        new_commits = fetcher.fetch(
            owner     = config.owner,
            repo      = config.repo,
            file_path = file_path,
            since_sha = last_sha
        )

        # Merge with cache
        if cache and new_commits:
            raw_new = cache.serialize_commits(new_commits)
            cached_data = cache.update_file(
                cached_data,
                file_path,
                raw_new,
                new_commits[0].commit_hash
            )

        # Rebuild full commit list from cache + new
        if cache:
            all_raw = cache.get_cached_commits(cached_data, file_path)
            commits = cache.deserialize_commits(file_path, all_raw)
        else:
            commits = new_commits

        if commits:
            file_commit_map[file_path] = commits

    # 6. Persist updated cache
    if cache:
        cache.save(config.owner, config.repo, cached_data)
        logger.info("Cache saved.")

    logger.info(
        f"Pipeline complete. "
        f"{len(file_commit_map)} files with commit history."
    )
    return file_commit_map