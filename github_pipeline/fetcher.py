import logging
from typing import Optional
from .client import GitHubClient
from .normalizer import CommitNormalizer
from knowledge_risk.models import FileCommit

logger = logging.getLogger(__name__)


# GraphQL query for commit history per file
# Faster than REST for metadata-only fetches
COMMIT_HISTORY_QUERY = """
query FileHistory(
  $owner: String!,
  $repo: String!,
  $path: String!,
  $cursor: String
) {
  repository(owner: $owner, name: $repo) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(path: $path, first: 100, after: $cursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              oid
              message
              committedDate
              author {
                email
                name
                user {
                  login
                }
              }
              deletions
              additions
            }
          }
        }
      }
    }
  }
}
"""


# GraphQL query to detect renames
RENAME_QUERY = """
query FileRenames($owner: String!, $repo: String!, $path: String!) {
  repository(owner: $owner, name: $repo) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(path: $path, first: 5) {
            nodes {
              oid
              committedDate
              parents(first: 1) {
                nodes {
                  oid
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


class CommitHistoryFetcher:
    """
    Fetches per-file commit history from GitHub.

    Strategy:
    - Uses GraphQL for commit metadata (fast, low request count)
    - Uses REST only when line-change stats are needed per commit
    - Follows renames via REST /commits?path= which GitHub resolves
    - Stops early when since_sha is encountered (incremental refresh)
    - Caps at max_commits to avoid unbounded fetches on old files
    """

    def __init__(self,
                 client: GitHubClient,
                 normalizer: CommitNormalizer,
                 max_commits: int = 500,
                 fetch_line_stats: bool = True):

        self.client           = client
        self.normalizer       = normalizer
        self.max_commits      = max_commits
        self.fetch_line_stats = fetch_line_stats


    # ── Public interface ───────────────────────────────────────────────────

    def fetch(self,
              owner: str,
              repo: str,
              file_path: str,
              since_sha: Optional[str] = None) -> list[FileCommit]:
        """
        Main entry point. Returns FileCommit list for a single file.
        Stops at since_sha if provided (incremental mode).
        Falls back to REST if GraphQL fails.
        """
        try:
            commits = self._fetch_via_graphql(
                owner, repo, file_path, since_sha
            )
        except Exception as e:
            logger.warning(
                f"GraphQL fetch failed for {file_path}: {e}. "
                "Falling back to REST."
            )
            commits = self._fetch_via_rest(
                owner, repo, file_path, since_sha
            )

        if not commits:
            logger.debug(f"No commits found for {file_path}")
            return []

        # Enrich with line stats if needed and not already populated
        if self.fetch_line_stats:
            commits = self._enrich_line_stats(
                owner, repo, file_path, commits
            )

        logger.debug(
            f"{file_path}: {len(commits)} commits fetched."
        )
        return commits


    # ── GraphQL fetch ──────────────────────────────────────────────────────

    def _fetch_via_graphql(self,
                           owner: str,
                           repo: str,
                           file_path: str,
                           since_sha: Optional[str]) -> list[FileCommit]:
        commits = []
        cursor  = None
        found_since = False

        while True:
            data = self.client.graphql(
                COMMIT_HISTORY_QUERY,
                variables={
                    "owner":  owner,
                    "repo":   repo,
                    "path":   file_path,
                    "cursor": cursor
                }
            )

            history = (
                data.get("repository", {})
                    .get("defaultBranchRef", {})
                    .get("target", {})
                    .get("history", {})
            )

            nodes     = history.get("nodes", [])
            page_info = history.get("pageInfo", {})

            for node in nodes:
                sha = node.get("oid", "")

                # Stop when we reach the last cached commit
                if since_sha and sha == since_sha:
                    found_since = True
                    break

                commit = self._node_to_filecommit(file_path, node)
                commits.append(commit)

                if len(commits) >= self.max_commits:
                    logger.debug(
                        f"{file_path}: hit max_commits "
                        f"({self.max_commits})."
                    )
                    return commits

            if found_since:
                break

            if not page_info.get("hasNextPage"):
                break

            cursor = page_info.get("endCursor")

        return commits


    def _node_to_filecommit(self,
                             file_path: str,
                             node: dict) -> FileCommit:
        """
        Convert a GraphQL commit history node to FileCommit.
        Line stats are 0 here — enriched separately via REST.
        """
        author_block = node.get("author", {}) or {}

        # Prefer GitHub login > email > name
        author = (
            (author_block.get("user") or {}).get("login")
            or author_block.get("email")
            or author_block.get("name")
            or "unknown"
        )

        from datetime import datetime
        try:
            ts = datetime.fromisoformat(
                node.get("committedDate", "").replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except ValueError:
            ts = datetime.now()

        return FileCommit(
            file_path    = file_path,
            author       = author,
            timestamp    = ts,
            lines_added  = node.get("additions", 0),
            lines_deleted= node.get("deletions", 0),
            commit_hash  = node.get("oid", "")[:12],
            message      = node.get("message", "")[:200]
        )


    # ── REST fallback ──────────────────────────────────────────────────────

    def _fetch_via_rest(self,
                        owner: str,
                        repo: str,
                        file_path: str,
                        since_sha: Optional[str]) -> list[FileCommit]:
        """
        REST fallback for when GraphQL fails or is unavailable.
        Also handles rename-following automatically — GitHub's
        /commits?path= endpoint resolves renames server-side.
        """
        commits = []
        params  = {
            "path":     file_path,
            "per_page": 100
        }

        all_raw = self.client.paginate(
            f"/repos/{owner}/{repo}/commits",
            params=params
        )

        for raw in all_raw:
            sha = raw.get("sha", "")

            if since_sha and sha == since_sha:
                break

            commit = self.normalizer.from_rest_commit(
                file_path  = file_path,
                commit     = raw,
                file_stats = {}   # enriched separately
            )
            commits.append(commit)

            if len(commits) >= self.max_commits:
                break

        return commits


    # ── Line stat enrichment ───────────────────────────────────────────────

    def _enrich_line_stats(self,
                           owner: str,
                           repo: str,
                           file_path: str,
                           commits: list[FileCommit]) -> list[FileCommit]:
        """
        GraphQL commit nodes expose repo-level additions/deletions,
        not per-file. For accurate HHI weighting we need per-file
        line stats, which requires a REST call per commit.

        To avoid hammering the API, we only enrich the most recent
        commits up to a sensible cap. Older commits contribute less
        to decayed recency anyway.
        """
        ENRICH_LIMIT = 50   # only enrich newest N commits

        enriched = []
        for i, commit in enumerate(commits):
            if i >= ENRICH_LIMIT:
                enriched.append(commit)
                continue

            try:
                data, _ = self.client.get(
                    f"/repos/{owner}/{repo}/commits/{commit.commit_hash}"
                )
                if not data:
                    enriched.append(commit)
                    continue

                # Find this file's stats in the commit
                files = data.get("files", [])
                file_stat = next(
                    (f for f in files
                     if f.get("filename") == file_path
                     or f.get("previous_filename") == file_path),
                    {}
                )

                # Rebuild with accurate line stats
                enriched.append(FileCommit(
                    file_path    = commit.file_path,
                    author       = commit.author,
                    timestamp    = commit.timestamp,
                    lines_added  = file_stat.get("additions",
                                                  commit.lines_added),
                    lines_deleted= file_stat.get("deletions",
                                                  commit.lines_deleted),
                    commit_hash  = commit.commit_hash,
                    message      = commit.message
                ))

            except Exception as e:
                logger.warning(
                    f"Could not enrich line stats for "
                    f"{commit.commit_hash}: {e}"
                )
                enriched.append(commit)

        return enriched


    # ── Rename detection ───────────────────────────────────────────────────

    def detect_previous_path(self,
                              owner: str,
                              repo: str,
                              file_path: str) -> Optional[str]:
        """
        Detects if a file was recently renamed.
        Returns the previous path if found, None otherwise.
        Useful for stitching together history across renames.
        """
        try:
            data, _ = self.client.get(
                f"/repos/{owner}/{repo}/commits",
                params={"path": file_path, "per_page": 5}
            )
            if not data:
                return None

            for commit_summary in data:
                sha = commit_summary.get("sha", "")
                detail, _ = self.client.get(
                    f"/repos/{owner}/{repo}/commits/{sha}"
                )
                if not detail:
                    continue

                for f in detail.get("files", []):
                    if (f.get("filename") == file_path
                            and f.get("status") == "renamed"):
                        prev = f.get("previous_filename")
                        logger.info(
                            f"Rename detected: "
                            f"{prev} → {file_path}"
                        )
                        return prev

        except Exception as e:
            logger.warning(f"Rename detection failed: {e}")

        return None