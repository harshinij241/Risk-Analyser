# github_pipeline/scanner.py

import fnmatch
import logging
from dataclasses import dataclass, field
from typing import Optional
from .client import GitHubClient
from knowledge_risk.filters import is_excluded_file, should_analyze

logger = logging.getLogger(__name__)


@dataclass
class ScanConfig:
    path_prefix:   Optional[str] = None
    max_files:     int           = 2000
    include_globs: list[str]     = field(default_factory=list)
    exclude_globs: list[str]     = field(default_factory=list)
    min_file_size: int           = 0


TREE_QUERY = """
query RepoTree($owner: String!, $repo: String!, $branch: String!) {
  repository(owner: $owner, name: $repo) {
    defaultBranchRef {
      name
    }
    object(expression: $branch) {
      ... on Tree {
        entries {
          path
          type
          object {
            ... on Blob {
              byteSize
            }
          }
        }
      }
    }
  }
}
"""


class RepoScanner:
    """
    Lists all files in a repo using a single GraphQL query.
    Applies path filters before returning.
    Much more efficient than paginating the REST tree API.
    """

    def __init__(self, client: GitHubClient, config: ScanConfig):
        self.client = client
        self.config = config

    def get_default_branch(self, owner: str, repo: str) -> str:
        data, _ = self.client.get(f"/repos/{owner}/{repo}")
        if not data:
            raise ValueError(f"Repository {owner}/{repo} not found or access denied.")
        return data.get("default_branch", "main")

    def scan(self, owner: str, repo: str) -> list[str]:
        branch = self.get_default_branch(owner, repo)

        logger.info(f"Scanning {owner}/{repo} on branch {branch}")

        data = self.client.graphql(
            TREE_QUERY,
            variables={
                "owner":  owner,
                "repo":   repo,
                "branch": f"{branch}:"
            }
        )

        entries = (
            data.get("repository", {})
                .get("object", {})
                .get("entries", [])
        )

        files = []
        for entry in entries:
            if entry["type"] != "blob":
                continue

            path = entry["path"]
            size = (entry.get("object") or {}).get("byteSize", 0)

            if not self._should_include(path, size):
                continue

            files.append(path)

            if len(files) >= self.config.max_files:
                logger.warning(
                    f"Hit max_files limit ({self.config.max_files}). "
                    "Consider using path_prefix to narrow scope."
                )
                break

        logger.info(f"Found {len(files)} files to analyze.")
        return files

    def _should_include(self, path: str, size: int) -> bool:
        # Path prefix filter
        if self.config.path_prefix:
            if not path.startswith(self.config.path_prefix):
                return False

        # Size filter
        if size < self.config.min_file_size:
            return False

        # Full classification — only source code passes
        if not should_analyze(path):
            return False

        # Custom include globs
        if self.config.include_globs:
            if not any(
                fnmatch.fnmatch(path, g)
                for g in self.config.include_globs
            ):
                return False

        # Custom exclude globs
        if any(
            fnmatch.fnmatch(path, g)
            for g in self.config.exclude_globs
        ):
            return False

        return True