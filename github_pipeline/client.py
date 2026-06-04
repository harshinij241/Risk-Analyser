import time
import logging
import asyncio
from dataclasses import dataclass
from typing import Optional, Any
from enum import Enum

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


# ── Token scope validation ─────────────────────────────────────────────────

REQUIRED_SCOPES_PUBLIC  = {"public_repo", "repo"}
REQUIRED_SCOPES_PRIVATE = {"repo"}

class RepoVisibility(Enum):
    PUBLIC  = "public"
    PRIVATE = "private"


@dataclass
class RateLimitState:
    remaining: int   = 5000
    reset_at:  float = 0.0    # unix timestamp
    used:      int   = 0


# ── Client ─────────────────────────────────────────────────────────────────

class GitHubClient:
    """
    Handles auth, retries, rate limits, and concurrency throttling.
    All other pipeline components receive an instance of this class
    and call .get() / .graphql() — nothing else.
    """

    REST_BASE    = "https://api.github.com"
    GRAPHQL_BASE = "https://api.github.com/graphql"

    def __init__(self,
                 token: str,
                 max_concurrency: int = 5,
                 max_retries: int = 3,
                 timeout: int = 30):

        self.token           = token
        self.timeout         = timeout
        self._semaphore      = asyncio.Semaphore(max_concurrency)
        self._rate           = RateLimitState()

        # Session with retry adapter for transient failures
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization":        f"Bearer {token}",
            "Accept":               "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=2,          # 1s, 2s, 4s
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("https://", adapter)


    # ── Startup validation ─────────────────────────────────────────────────

    def validate_token(self, visibility: RepoVisibility) -> None:
        """
        Fail fast at startup if token lacks required scope.
        Much better than discovering auth issues after 3,000 requests.
        """
        resp = self._session.get(
            f"{self.REST_BASE}/user",
            timeout=self.timeout
        )

        if resp.status_code == 401:
            raise PermissionError(
                "GitHub token is invalid or expired. "
                "Generate a new token at https://github.com/settings/tokens"
            )

        scopes = set(
            resp.headers.get("X-OAuth-Scopes", "").split(", ")
        )
        scopes = {s.strip() for s in scopes if s.strip()}

        required = (
            REQUIRED_SCOPES_PRIVATE
            if visibility == RepoVisibility.PRIVATE
            else REQUIRED_SCOPES_PUBLIC
        )

        if not required.intersection(scopes):
            raise PermissionError(
                f"Token is missing required scope. "
                f"Need one of: {required}. "
                f"Current scopes: {scopes or 'none'}. "
                f"Update at https://github.com/settings/tokens"
            )

        logger.info(f"Token validated. Scopes: {scopes}")
        self._update_rate_limit(resp.headers)


    # ── Rate limit management ──────────────────────────────────────────────

    def _update_rate_limit(self, headers: dict) -> None:
        """Read and store rate limit state from every response."""
        try:
            self._rate.remaining = int(
                headers.get("X-RateLimit-Remaining", self._rate.remaining)
            )
            self._rate.reset_at = float(
                headers.get("X-RateLimit-Reset", self._rate.reset_at)
            )
            self._rate.used = int(
                headers.get("X-RateLimit-Used", self._rate.used)
            )
        except (ValueError, TypeError):
            pass

    def _wait_if_needed(self) -> None:
        """
        Block if rate limit is nearly exhausted.
        Waits until reset window opens with a small buffer.
        """
        if self._rate.remaining <= 50:
            wait = max(0, self._rate.reset_at - time.time()) + 5
            logger.warning(
                f"Rate limit low ({self._rate.remaining} remaining). "
                f"Waiting {wait:.0f}s for reset."
            )
            time.sleep(wait)

    def _handle_secondary_limit(self, resp: requests.Response) -> bool:
        """
        Returns True if we hit a secondary limit and should retry.
        Secondary limits return 403 with a specific message,
        or 429 with Retry-After header.
        """
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            logger.warning(
                f"Secondary rate limit hit (429). "
                f"Waiting {retry_after}s."
            )
            time.sleep(retry_after)
            return True

        if resp.status_code == 403:
            body = resp.json() if resp.content else {}
            msg  = body.get("message", "")
            if "secondary rate limit" in msg.lower():
                logger.warning(
                    "Secondary rate limit hit (403). Waiting 60s."
                )
                time.sleep(60)
                return True

        return False


    # ── REST interface ─────────────────────────────────────────────────────

    def get(self,
            path: str,
            params: Optional[dict] = None,
            etag: Optional[str] = None) -> tuple[Any, dict]:
        """
        Synchronous GET with rate limit awareness.
        Returns (parsed_json, response_headers).
        Passes ETag for conditional requests if provided.
        Returns (None, headers) on 304 Not Modified.
        """
        self._wait_if_needed()

        headers = {}
        if etag:
            headers["If-None-Match"] = etag

        url = f"{self.REST_BASE}{path}"

        for attempt in range(3):
            resp = self._session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout
            )
            self._update_rate_limit(resp.headers)

            if resp.status_code == 304:
                # Not modified — cached response is still valid
                return None, dict(resp.headers)

            if self._handle_secondary_limit(resp):
                continue   # retry after wait

            if resp.status_code == 404:
                logger.debug(f"404 for {url} — skipping.")
                return None, dict(resp.headers)

            resp.raise_for_status()
            return resp.json(), dict(resp.headers)

        raise RuntimeError(f"Failed to GET {url} after 3 attempts")


    def paginate(self,
                 path: str,
                 params: Optional[dict] = None) -> list[Any]:
        """
        Fetches all pages for a paginated REST endpoint.
        Handles Link header navigation automatically.
        """
        results = []
        params  = params or {}
        params.setdefault("per_page", 100)

        url = f"{self.REST_BASE}{path}"

        while url:
            self._wait_if_needed()

            resp = self._session.get(
                url,
                params=params,
                timeout=self.timeout
            )
            self._update_rate_limit(resp.headers)

            if self._handle_secondary_limit(resp):
                continue

            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)

            # Follow Link: <url>; rel="next" header
            url    = None
            params = {}   # params are encoded in next URL already
            links  = resp.headers.get("Link", "")
            for part in links.split(","):
                part = part.strip()
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
                    break

        return results


    # ── GraphQL interface ──────────────────────────────────────────────────

    def graphql(self, query: str,
                variables: Optional[dict] = None) -> dict:
        """
        Execute a GraphQL query.
        Handles rate limits and retries same as REST.
        """
        self._wait_if_needed()

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        for attempt in range(3):
            resp = self._session.post(
                self.GRAPHQL_BASE,
                json=payload,
                timeout=self.timeout
            )
            self._update_rate_limit(resp.headers)

            if self._handle_secondary_limit(resp):
                continue

            resp.raise_for_status()
            data = resp.json()

            # GraphQL errors come back as 200 with an errors key
            if "errors" in data:
                errors = data["errors"]
                # Check if it's a rate limit error specifically
                if any("rate limit" in str(e).lower() for e in errors):
                    wait = max(
                        0, self._rate.reset_at - time.time()
                    ) + 5
                    logger.warning(
                        f"GraphQL rate limit. Waiting {wait:.0f}s."
                    )
                    time.sleep(wait)
                    continue
                raise RuntimeError(
                    f"GraphQL errors: {errors}"
                )

            return data.get("data", {})

        raise RuntimeError("GraphQL query failed after 3 attempts")


    # ── Async wrapper ──────────────────────────────────────────────────────

    async def get_async(self,
                        path: str,
                        params: Optional[dict] = None) -> Any:
        """
        Async wrapper with semaphore for concurrency control.
        Use this when fetching many files concurrently.
        The semaphore enforces max_concurrency set at init.
        """
        async with self._semaphore:
            loop = asyncio.get_event_loop()
            data, _ = await loop.run_in_executor(
                None, lambda: self.get(path, params)
            )
            return data


    # ── Diagnostics ────────────────────────────────────────────────────────

    def rate_limit_status(self) -> dict:
        """Call anytime to check current rate limit state."""
        data, _ = self.get("/rate_limit")
        return {
            "core": data["resources"]["core"],
            "graphql": data["resources"]["graphql"],
            "remaining": self._rate.remaining,
            "reset_in_seconds": max(
                0, self._rate.reset_at - time.time()
            )
        }