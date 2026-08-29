from __future__ import annotations

from typing import Any

import pytest


def _make_post(
    post_id: str,
    *,
    name: str | None = None,
    featured_at: str = "2026-06-02T12:00:00Z",
    votes: int = 100,
    tagline: str = "AI agents for teams",
) -> dict[str, Any]:
    return {
        "id": post_id,
        "name": name or f"Product {post_id}",
        "slug": (name or f"product-{post_id}").lower().replace(" ", "-"),
        "tagline": tagline,
        "description": "A reproducible test product",
        "url": f"https://www.producthunt.com/posts/{post_id}",
        "website": f"https://example.com/{post_id}",
        "votesCount": votes,
        "commentsCount": 10,
        "reviewsCount": 2,
        "reviewsRating": 4.5,
        "featuredAt": featured_at,
        "createdAt": featured_at,
        "topics": {
            "edges": [{"node": {"id": "topic-1", "name": "Artificial Intelligence", "slug": "ai"}}]
        },
    }


@pytest.fixture
def make_post():
    return _make_post
