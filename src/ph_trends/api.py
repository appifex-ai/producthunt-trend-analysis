from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

POSTS_QUERY = """
query Posts($first: Int!, $after: String, $postedAfter: DateTime!, $postedBefore: DateTime!) {
  posts(
    first: $first
    after: $after
    featured: true
    order: NEWEST
    postedAfter: $postedAfter
    postedBefore: $postedBefore
  ) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        name
        slug
        tagline
        description
        url
        website
        votesCount
        commentsCount
        featuredAt
        createdAt
      }
    }
  }
}
"""


class ProductHuntAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class Page:
    posts: list[dict[str, Any]]
    has_next_page: bool
    end_cursor: str | None
    total_count: int | None = None


def seconds_until_reset(value: str | None, now: float) -> float:
    if not value:
        return 60.0
    try:
        numeric = float(value)
    except ValueError:
        try:
            reset_at = parsedate_to_datetime(value)
            if reset_at.tzinfo is None:
                reset_at = reset_at.replace(tzinfo=UTC)
            return max(0.0, reset_at.timestamp() - now)
        except (TypeError, ValueError):
            try:
                reset_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return max(0.0, reset_at.timestamp() - now)
            except ValueError:
                return 60.0
    if numeric >= 1_000_000_000:
        return max(0.0, numeric - now)
    return max(0.0, numeric)


class ProductHuntClient:
    def __init__(
        self,
        *,
        token: str,
        api_url: str,
        page_size: int = 20,
        page_delay_seconds: float = 0.25,
        rate_limit_reserve: int = 250,
        max_retries: int = 6,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
    ) -> None:
        if not 1 <= page_size <= 20:
            raise ValueError("Product Hunt API page_size must be between 1 and 20")
        if page_delay_seconds < 0 or rate_limit_reserve < 0:
            raise ValueError("page delay and rate-limit reserve must be non-negative")
        parsed_url = urlparse(api_url)
        if transport is None and (
            parsed_url.scheme != "https" or parsed_url.hostname != "api.producthunt.com"
        ):
            raise ValueError("API URL must be https://api.producthunt.com")
        self.page_size = page_size
        self.page_delay_seconds = page_delay_seconds
        self.rate_limit_reserve = rate_limit_reserve
        self.max_retries = max_retries
        self._sleep = sleep
        self._now = now
        self._api_url = api_url
        self.query_fingerprint = sha256(
            f"{POSTS_QUERY}\npage_size={page_size}".encode()
        ).hexdigest()
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(45.0),
            transport=transport,
        )
        self.request_count = 0
        self.estimated_query_cost = 0
        self.rate_limit: dict[str, Any] = {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ProductHuntClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _update_rate_limit(self, response: httpx.Response) -> None:
        previous_remaining = self.rate_limit.get("remaining")

        def as_int(name: str) -> int | None:
            value = response.headers.get(name)
            try:
                return int(value) if value is not None else None
            except ValueError:
                return None

        remaining = as_int("x-rate-limit-remaining")
        if (
            previous_remaining is not None
            and remaining is not None
            and remaining <= previous_remaining
        ):
            self.estimated_query_cost = max(
                self.estimated_query_cost, previous_remaining - remaining
            )
        self.rate_limit = {
            "limit": as_int("x-rate-limit-limit"),
            "remaining": remaining,
            "reset": response.headers.get("x-rate-limit-reset"),
        }

    def _wait_for_capacity(self) -> None:
        remaining = self.rate_limit.get("remaining")
        threshold = self.rate_limit_reserve + self.estimated_query_cost
        if remaining is not None and remaining <= threshold:
            wait = seconds_until_reset(self.rate_limit.get("reset"), self._now()) + 1.0
            logger.info(
                "Rate-limit reserve reached (%s remaining); waiting %.0f seconds",
                remaining,
                wait,
            )
            self._sleep(wait)

    def fetch_posts_page(self, *, start: str, end: str, after: str | None = None) -> Page:
        self._wait_for_capacity()
        payload = {
            "query": POSTS_QUERY,
            "variables": {
                "first": self.page_size,
                "after": after,
                "postedAfter": start,
                "postedBefore": end,
            },
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if attempt:
                backoff = min(60.0, 2 ** (attempt - 1)) + random.uniform(0, 0.25)
                self._sleep(backoff)
            try:
                response = self._client.post(self._api_url, json=payload)
                self.request_count += 1
                self._update_rate_limit(response)
                if response.status_code == 429:
                    retry_after = response.headers.get("retry-after")
                    wait = (
                        max(
                            seconds_until_reset(retry_after, self._now()),
                            seconds_until_reset(self.rate_limit.get("reset"), self._now()),
                        )
                        + 1.0
                    )
                    logger.warning("Product Hunt returned 429; waiting %.0f seconds", wait)
                    self._sleep(wait)
                    continue
                if response.status_code >= 500:
                    last_error = ProductHuntAPIError(
                        f"Product Hunt returned HTTP {response.status_code}"
                    )
                    continue
                response.raise_for_status()
                body = response.json()
                if body.get("errors"):
                    details = "; ".join(
                        error.get("error_description")
                        or error.get("message")
                        or error.get("error")
                        or "unknown GraphQL error"
                        for error in body["errors"]
                    )
                    raise ProductHuntAPIError(details)
                connection = body["data"]["posts"]
                page_info = connection["pageInfo"]
                if self.page_delay_seconds:
                    self._sleep(self.page_delay_seconds)
                return Page(
                    posts=[edge["node"] for edge in connection["edges"]],
                    has_next_page=bool(page_info["hasNextPage"]),
                    end_cursor=page_info.get("endCursor"),
                    total_count=int(connection["totalCount"]),
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                continue

        raise ProductHuntAPIError(
            f"Product Hunt request failed after {self.max_retries + 1} attempts: {last_error}"
        )
