"""GitHub REST client for star timestamps (ground truth for capture-rate checks).

Uses ``GET /repositories/{repo_id}/stargazers`` (keyed on the immutable repo id, never the name)
with ``Accept: application/vnd.github.star+json`` so each entry carries ``starred_at``.
The API only lists *current* stargazers, so users who unstarred are absent.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from breakout.logging import get_logger

log = get_logger(__name__)

API = "https://api.github.com"
STAR_ACCEPT = "application/vnd.github.star+json"
_LAST_PAGE = re.compile(r'<[^>]*[?&]page=(\d+)[^>]*>;\s*rel="last"')


@dataclass(frozen=True)
class Star:
    user_id: int
    starred_at: datetime  # naive UTC


class RepoGone(Exception):
    """404/403-blocked/451 repository (deleted, private, DMCA)."""


class _Transient(Exception):
    pass


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)


class GitHubClient:
    def __init__(self, token: str, *, client: httpx.Client | None = None, min_remaining: int = 20):
        if not token:
            raise ValueError("a GitHub token is required (GH_ENRICH_TOKEN)")
        self._client = client or httpx.Client(timeout=httpx.Timeout(30.0))
        self._headers = {
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._min_remaining = min_remaining
        self.requests = 0

    def close(self) -> None:
        self._client.close()

    def _get(
        self, url: str, params: dict | None = None, accept: str | None = None
    ) -> httpx.Response:
        headers = {**self._headers, "Accept": accept or "application/vnd.github+json"}

        @retry(
            retry=retry_if_exception(lambda e: isinstance(e, _Transient)),
            stop=stop_after_attempt(6),
            wait=wait_exponential(multiplier=1, max=30),
            reraise=True,
        )
        def once() -> httpx.Response:
            self.requests += 1
            try:
                r = self._client.get(url, params=params, headers=headers)
            except httpx.TransportError as exc:
                raise _Transient(str(exc)) from exc
            if r.status_code >= 500:
                raise _Transient(f"HTTP {r.status_code}")
            if r.status_code in (403, 429) and (
                r.headers.get("x-ratelimit-remaining") == "0" or "retry-after" in r.headers
            ):
                reset = r.headers.get("x-ratelimit-reset")
                wait = int(r.headers.get("retry-after", 0)) or (
                    max(int(reset) - int(time.time()), 1) + 1 if reset else 60
                )
                log.warning("rate limited; sleeping %ss", min(wait, 3700))
                time.sleep(min(wait, 3700))
                raise _Transient("rate limited")
            return r

        r = once()
        if (
            r.headers.get("x-ratelimit-remaining")
            and int(r.headers["x-ratelimit-remaining"]) < self._min_remaining
        ):
            reset = int(r.headers.get("x-ratelimit-reset", 0))
            time.sleep(min(max(reset - int(time.time()), 1) + 1, 3700))
        return r

    def search_repos(
        self, query: str, *, max_results: int = 300, sort: str = "stars"
    ) -> list[dict]:
        """Search repositories; returns ``{id, full_name, stargazers_count, created_at}`` dicts."""
        out: list[dict] = []
        page = 1
        while len(out) < max_results and page <= 10:
            r = self._get(
                f"{API}/search/repositories",
                {"q": query, "sort": sort, "order": "desc", "per_page": 100, "page": page},
            )
            if r.status_code == 422:  # beyond the 1000-result window
                break
            r.raise_for_status()
            items = r.json().get("items", [])
            out.extend(
                {
                    "id": i["id"],
                    "full_name": i["full_name"],
                    "stargazers_count": i["stargazers_count"],
                    "created_at": i["created_at"],
                    "fork": i["fork"],
                }
                for i in items
            )
            if len(items) < 100:
                break
            page += 1
            time.sleep(2.1)  # search API: 30 requests / minute
        return out[:max_results]

    def stargazers(
        self, repo_id: int, *, since: datetime | None = None, max_pages: int = 100
    ) -> Iterator[Star]:
        """All stargazers (or those starred at/after ``since``), newest-last order per GitHub.

        With ``since`` set, pages are read from the last page backwards and the walk stops once a
        whole page is older than ``since``: cheap for popular repos when only recent stars matter.
        """
        url = f"{API}/repositories/{repo_id}/stargazers"
        base = {"per_page": 100}
        first = self._get(url, {**base, "page": 1}, accept=STAR_ACCEPT)
        if first.status_code in (404, 403, 451):
            raise RepoGone(f"repo {repo_id}: HTTP {first.status_code}")
        first.raise_for_status()
        m = _LAST_PAGE.search(first.headers.get("link", ""))
        last = int(m.group(1)) if m else 1
        if since is None:
            pages = list(range(1, min(last, max_pages) + 1))
        else:
            pages = list(range(last, max(last - max_pages, 0), -1))
        for p in pages:
            r = first if p == 1 else self._get(url, {**base, "page": p}, accept=STAR_ACCEPT)
            r.raise_for_status()
            items = r.json()
            stars = [
                Star(i["user"]["id"], _parse_ts(i["starred_at"]))
                for i in items
                if i.get("user") and i.get("starred_at")
            ]
            yield from stars
            if since is not None and stars and max(s.starred_at for s in stars) < since:
                break
