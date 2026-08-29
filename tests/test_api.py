from __future__ import annotations

import httpx

from ph_trends.api import ProductHuntClient, seconds_until_reset


def test_fetch_page_and_parse_rate_limit(make_post) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            headers={"x-rate-limit-limit": "6250", "x-rate-limit-remaining": "6100"},
            json={
                "data": {
                    "posts": {
                        "totalCount": 1,
                        "pageInfo": {"hasNextPage": False, "endCursor": "end"},
                        "edges": [{"node": make_post("1")}],
                    }
                }
            },
        )

    client = ProductHuntClient(
        token="secret",
        api_url="https://api.example.test/graphql",
        page_delay_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    page = client.fetch_posts_page(start="2026-01-01", end="2026-02-01")
    client.close()
    assert page.posts[0]["id"] == "1"
    assert page.end_cursor == "end"
    assert page.total_count == 1
    assert client.request_count == 1
    assert client.rate_limit["remaining"] == 6100


def test_retries_429_and_waits(make_post) -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"retry-after": "2", "x-rate-limit-reset": "10"},
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "posts": {
                        "totalCount": 1,
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "edges": [{"node": make_post("2")}],
                    }
                }
            },
        )

    client = ProductHuntClient(
        token="secret",
        api_url="https://api.example.test/graphql",
        page_delay_seconds=0,
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        now=lambda: 100.0,
    )
    page = client.fetch_posts_page(start="2026-01-01", end="2026-02-01")
    client.close()
    assert page.posts[0]["id"] == "2"
    assert attempts == 2
    assert any(wait >= 11 for wait in sleeps)


def test_seconds_until_reset_supports_epoch_and_delta() -> None:
    assert seconds_until_reset("1700000115", 1700000100) == 15
    assert seconds_until_reset("5", 100) == 5


def test_rejects_non_product_hunt_url_without_test_transport() -> None:
    try:
        ProductHuntClient(token="secret", api_url="https://example.com/graphql")
    except ValueError as exc:
        assert "api.producthunt.com" in str(exc)
    else:
        raise AssertionError("unsafe API URL was accepted")
