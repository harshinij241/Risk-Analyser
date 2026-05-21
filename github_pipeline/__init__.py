from .client import GitHubClient, RepoVisibility, RateLimitState
from .scanner import RepoScanner, ScanConfig
from .fetcher import CommitHistoryFetcher
from .normalizer import CommitNormalizer
from .cache import CacheStore
from .pipeline import build_file_commit_map, PipelineConfig

__version__ = "0.1.0"

__all__ = [
    # Main entry point
    "build_file_commit_map",

    # Config
    "PipelineConfig",
    "ScanConfig",

    # Components (exposed for testing and custom pipelines)
    "GitHubClient",
    "RepoVisibility",
    "RateLimitState",
    "RepoScanner",
    "CommitHistoryFetcher",
    "CommitNormalizer",
    "CacheStore",
]