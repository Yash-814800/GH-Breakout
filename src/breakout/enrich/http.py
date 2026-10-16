"""Shared HTTP plumbing for enrichment: client factory, throttle, retries, rate-limit helpers.

Rules (CLAUDE.md section 10, phase 4 gotchas):
- the GitHub token is attached only to requests for ``api.github.com`` and is never logged;
- at most ``max_rps`` requests per second per client;
- GraphQL ``rateLimit`` and REST ``x-ratelimit-*`` / ``retry-after`` headers are honoured;
- time is injectable (``Clock``) so sleep logic is unit-testable without waiting.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from breakout.logging import get_logger

log = get_logger(__name__)

GITHUB_API_HOST = "api.github.com"
GITHUB_API = f"https://{GITHUB_API_HOST}"
LOW_WATER = 100  # sleep until reset when fewer requests than this remain
MAX_SLEEP = 3700.0  # never sleep longer than one hour plus slack


class Clock(Protocol):
    def time(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def time(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


@dataclass
class FakeClock:
    """Deterministic clock for tests: ``sleep`` advances ``now`` and records the request."""

    now: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += max(seconds, 0.0)


def user_agent(repo_url: str) -> str:
    return f"gh-breakout (+{repo_url})"


def make_client(
    repo_url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    timeout: float = 30.0,
) -> httpx.Client:
    """One ``httpx.Client`` with project user agent and timeouts; no credentials attached."""
    return httpx.Client(
        headers={"User-Agent": user_agent(repo_url)},
        timeout=httpx.Timeout(timeout),
        follow_redirects=True,
        transport=transport,
    )


class Throttle:
    """Spaces calls at least ``1 / max_rps`` seconds apart."""

    def __init__(self, max_rps: float, clock: Clock | None = None):
        if max_rps <= 0:
            raise ValueError("max_rps must be > 0")
        self._interval = 1.0 / max_rps
        self._clock = clock or SystemClock()
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        """Reserve the next slot (thread-safe) and sleep until it arrives."""
        with self._lock:
            now = self._clock.time()
            slot = max(now, self._next)
            self._next = slot + self._interval
        if slot > now:
            self._clock.sleep(slot - now)


def seconds_until_reset(reset_epoch: float, now: float) -> float:
    """Seconds to sleep until a rate-limit reset (plus 1 s slack), capped at ``MAX_SLEEP``."""
    return min(max(reset_epoch - now, 0.0) + 1.0, MAX_SLEEP)


def rest_wait_seconds(headers: httpx.Headers | dict[str, str], now: float) -> float:
    """How long to sleep after a REST response, from its headers (0 when none is needed).

    ``retry-after`` (secondary limit) wins; otherwise sleep to ``x-ratelimit-reset`` when
    ``x-ratelimit-remaining`` fell below :data:`LOW_WATER`.
    """
    h = {k.lower(): v for k, v in headers.items()}
    if "retry-after" in h:
        try:
            return min(float(h["retry-after"]) + 1.0, MAX_SLEEP)
        except ValueError:
            return 60.0
    rem, reset = h.get("x-ratelimit-remaining"), h.get("x-ratelimit-reset")
    if rem is not None and reset is not None:
        try:
            if int(rem) < LOW_WATER:
                return seconds_until_reset(float(reset), now)
        except ValueError:
            return 0.0
    return 0.0


def graphql_wait_seconds(rate_limit: dict[str, Any] | None, now: float) -> float:
    """Sleep needed given a GraphQL ``rateLimit { remaining resetAt }`` object."""
    if not rate_limit:
        return 0.0
    remaining = rate_limit.get("remaining")
    reset_at = rate_limit.get("resetAt")
    if remaining is None or reset_at is None or remaining >= LOW_WATER:
        return 0.0
    from datetime import UTC, datetime

    reset = datetime.fromisoformat(str(reset_at).replace("Z", "+00:00")).astimezone(UTC)
    return seconds_until_reset(reset.timestamp(), now)


class TransientError(Exception):
    """Retryable failure (5xx, transport error, secondary rate limit)."""


class GitHubApi:
    """Throttled, retrying GitHub API caller (REST + GraphQL) that sends the token only to
    ``api.github.com``. ``requests`` counts every HTTP attempt."""

    def __init__(
        self,
        token: str,
        *,
        client: httpx.Client,
        max_rps: float = 1.0,
        clock: Clock | None = None,
        attempts: int = 6,
    ):
        if not token:
            raise ValueError("a GitHub token is required (GH_ENRICH_TOKEN)")
        self._token = token
        self._client = client
        self.clock = clock or SystemClock()
        self._throttle = Throttle(max_rps, self.clock)
        self._attempts = attempts
        self.requests = 0
        self._count_lock = threading.Lock()

    def __repr__(self) -> str:  # never leak the token
        return f"GitHubApi(requests={self.requests})"

    def close(self) -> None:
        self._client.close()

    def _headers(self, url: str) -> dict[str, str]:
        host = urlparse(url).hostname
        if host != GITHUB_API_HOST:
            return {}
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _send(self, method: str, url: str, **kw: Any) -> httpx.Response:
        def once() -> httpx.Response:
            self._throttle.wait()
            with self._count_lock:
                self.requests += 1
            try:
                r = self._client.request(method, url, headers=self._headers(url), **kw)
            except httpx.TransportError as exc:
                raise TransientError(type(exc).__name__) from exc
            if r.status_code >= 500:
                raise TransientError(f"HTTP {r.status_code}")
            if r.status_code in (403, 429):
                wait = rest_wait_seconds(r.headers, self.clock.time())
                if wait > 0 or r.headers.get("x-ratelimit-remaining") == "0":
                    wait = wait or 60.0
                    log.warning("rate limited (HTTP %s); sleeping %.0fs", r.status_code, wait)
                    self.clock.sleep(wait)
                    raise TransientError("rate limited")
            return r

        retrying = Retrying(
            retry=retry_if_exception(lambda e: isinstance(e, TransientError)),
            stop=stop_after_attempt(self._attempts),
            wait=wait_exponential(multiplier=1, max=30),
            sleep=self.clock.sleep,
            reraise=True,
        )
        r: httpx.Response = retrying(once)
        wait = rest_wait_seconds(r.headers, self.clock.time())
        if wait > 0:
            log.info("rate limit low; sleeping %.0fs until reset", wait)
            self.clock.sleep(wait)
        return r

    def rest_get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        url = path if path.startswith("http") else f"{GITHUB_API}{path}"
        return self._send("GET", url, params=params)

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST a GraphQL query; returns the decoded JSON body (``data`` and ``errors`` kept:
        partial results with per-alias NOT_FOUND errors are normal for batched lookups)."""
        r = self._send(
            "POST", f"{GITHUB_API}/graphql", json={"query": query, "variables": variables or {}}
        )
        r.raise_for_status()
        body: dict[str, Any] = r.json()
        wait = graphql_wait_seconds(((body.get("data") or {}).get("rateLimit")), self.clock.time())
        if wait > 0:
            log.info("graphql rate limit low; sleeping %.0fs until reset", wait)
            self.clock.sleep(wait)
        return body
