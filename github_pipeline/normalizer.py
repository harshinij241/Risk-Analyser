import logging
from datetime import datetime, timezone

from knowledge_risk.models import FileCommit

logger = logging.getLogger(__name__)

BOT_EMAIL_PATTERNS = [
    "noreply@github.com",
    "bot@",
    "no-reply@",
    "actions@"
]


class CommitNormalizer:
    """
    Pure data transformation — no API calls.
    Converts raw GitHub API commit payloads into FileCommit objects.
    """

    def from_rest_commit(self,
                         file_path: str,
                         commit: dict,
                         file_stats: dict) -> FileCommit:
        """
        Builds FileCommit from REST /commits endpoint response.
        commit: the commit object from the API
        file_stats: the per-file entry from commit["files"]
        """
        author = self._extract_author(commit)
        ts = self._extract_timestamp(commit)

        return FileCommit(
            file_path=file_path,
            author=author,
            timestamp=ts,
            lines_added=file_stats.get("additions", 0),
            lines_deleted=file_stats.get("deletions", 0),
            commit_hash=commit.get("sha", "")[:12],
            message=(
                commit.get("commit", {})
                      .get("message", "")[:200]
            )
        )

    def from_graphql_commit(self,
                            file_path: str,
                            node: dict) -> FileCommit:
        """
        Builds FileCommit from GraphQL commit history node.
        Note: GraphQL doesn't expose per-file line stats —
        those require a REST call. Lines default to 0 here.
        """

        author_info = node.get("author", {})

        # Prefer GitHub username/login over email over name
        author = (
            (author_info.get("user") or {}).get("login")
            or author_info.get("email")
            or author_info.get("name")
            or "unknown"
        )

        try:
            ts = datetime.fromisoformat(
                node.get("committedDate", "").replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except (ValueError, AttributeError):
            logger.warning(
                "Could not parse GraphQL timestamp, using now."
            )
            ts = datetime.now()

        return FileCommit(
            file_path=file_path,
            author=author,
            timestamp=ts,
            lines_added=0,   # enriched later via REST if needed
            lines_deleted=0,
            commit_hash=node.get("oid", "")[:12],
            message=node.get("message", "")[:200]
        )

    def _extract_author(self, commit: dict) -> str:
        """
        Prefer login (GitHub username) over email over name.
        Username is the most stable identifier across account changes.
        """

        # GitHub user object (present if author has a GitHub account)
        login = (
            commit.get("author", {}) or {}
        ).get("login")

        if login:
            return login

        # Fall back to git author email
        email = (
            commit.get("commit", {})
                  .get("author", {})
                  .get("email", "")
        )

        if email and not self._is_bot_email(email):
            return email

        # Fall back to git author name
        return (
            commit.get("commit", {})
                  .get("author", {})
                  .get("name", "unknown")
        )

    def _extract_timestamp(self, commit: dict) -> datetime:
        raw = (
            commit.get("commit", {})
                  .get("author", {})
                  .get("date", "")
        )

        try:
            return datetime.fromisoformat(
                raw.replace("Z", "+00:00")
            ).replace(tzinfo=None)

        except (ValueError, AttributeError):
            logger.warning(
                f"Could not parse timestamp '{raw}', using now."
            )
            return datetime.now()

    def _is_bot_email(self, email: str) -> bool:
        return any(
            pattern in email.lower()
            for pattern in BOT_EMAIL_PATTERNS
        )