from __future__ import annotations

import csv

import pytest

from ph_trends.visualization import REQUIRED_CATEGORIES, load_industry_evolution


def test_load_industry_evolution_decomposes_mcp(tmp_path) -> None:
    monthly = tmp_path / "monthly.csv"
    trends = tmp_path / "trends.csv"
    matches = tmp_path / "matches.csv"
    _write_csv(
        monthly,
        ["month", "featured_posts", "median_votes"],
        [
            {"month": "2026-01", "featured_posts": 10, "median_votes": 100},
            {"month": "2026-02", "featured_posts": 20, "median_votes": 80},
        ],
    )
    trend_rows = []
    for category in REQUIRED_CATEGORIES:
        trend_rows.extend(
            [
                {
                    "month": "2026-01",
                    "category": category,
                    "population_share": 0.1,
                    "top_decile_lift": "",
                    "posts": 1,
                },
                {
                    "month": "2026-02",
                    "category": category,
                    "population_share": 0.2,
                    "top_decile_lift": 1.5,
                    "posts": 4,
                },
            ]
        )
    _write_csv(
        trends,
        ["month", "category", "population_share", "top_decile_lift", "posts"],
        trend_rows,
    )
    _write_csv(
        matches,
        ["month", "category", "name", "matched_terms", "url"],
        [
            {
                "month": "2026-01",
                "category": "harness_infrastructure",
                "name": "One",
                "matched_terms": "mcp",
                "url": "https://example.com/one",
            },
            {
                "month": "2026-02",
                "category": "harness_infrastructure",
                "name": "Two",
                "matched_terms": "mcp | agent memory",
                "url": "https://example.com/two",
            },
            {
                "month": "2026-02",
                "category": "harness_infrastructure",
                "name": "Three",
                "matched_terms": "agent memory",
                "url": "https://example.com/three",
            },
        ],
    )

    data = load_industry_evolution(trends, monthly, matches)

    assert data.months == ("2026-01", "2026-02")
    assert data.mcp_posts == (1, 1)
    assert data.mcp_shares == (0.1, 0.05)
    assert data.category_lifts["agent_identity"] == (None, 1.5)


def test_load_industry_evolution_rejects_inconsistent_coverage(tmp_path) -> None:
    monthly = tmp_path / "monthly.csv"
    trends = tmp_path / "trends.csv"
    matches = tmp_path / "matches.csv"
    _write_csv(
        monthly,
        ["month", "featured_posts", "median_votes"],
        [{"month": "2026-01", "featured_posts": 10, "median_votes": 100}],
    )
    _write_csv(
        trends,
        ["month", "category", "population_share", "top_decile_lift", "posts"],
        [
            {
                "month": "2026-01",
                "category": "agent_identity",
                "population_share": 0.1,
                "top_decile_lift": 1.0,
                "posts": 1,
            }
        ],
    )
    _write_csv(matches, ["month", "category", "name", "matched_terms", "url"], [])

    with pytest.raises(ValueError, match="harness_infrastructure"):
        load_industry_evolution(trends, monthly, matches)


def _write_csv(path, fieldnames, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
