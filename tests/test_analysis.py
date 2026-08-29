from __future__ import annotations

import csv
from datetime import date

import pytest

from ph_trends.analysis import analyze, find_products
from ph_trends.api import Page
from ph_trends.db import connect
from ph_trends.sync import sync_range
from ph_trends.taxonomy import Taxonomy


class Client:
    request_count = 1
    rate_limit = {}

    def __init__(self, posts):
        self.posts = posts

    def fetch_posts_page(self, **_):
        return Page(self.posts, False, None)


def test_analysis_and_product_rank(tmp_path, make_post) -> None:
    connection = connect(tmp_path / "test.sqlite3")
    posts = [
        make_post(
            str(index),
            name="Vokal" if index == 4 else f"Product {index}",
            votes=index * 100,
            tagline="AI agents as teammates" if index == 4 else "A useful design tool",
        )
        for index in range(1, 11)
    ]
    sync_range(connection, Client(posts), start=date(2026, 6, 1), end=date(2026, 7, 1))
    output = tmp_path / "report"
    result = analyze(connection, year=2026, output_dir=output, allow_partial=True)
    assert result.posts == 10
    assert (output / "report.md").exists()
    assert (output / "theme_timelines.csv").exists()
    assert (output / "category_matches.csv").exists()
    assert (output / "external_events.csv").exists()
    with (output / "monthly_summary.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["featured_posts"] == "10"
    match = find_products(connection, "vokal")[0]
    assert match["month_rank"] == 7
    assert match["month_count"] == 10
    assert match["percentile"] == 33.3


def test_taxonomy_classifies_human_agent_team(make_post) -> None:
    matches = Taxonomy.load().classify(
        {
            "name": "Vokal",
            "tagline": "A shared workspace for humans and AI agents",
            "description": "Agents as teammates for your company",
            "topics": ["Artificial Intelligence"],
        }
    )
    assert "agent_identity" in matches
    assert "ai_coworkers" in matches
    assert "human_agent_organization" in matches


def test_analysis_rejects_incomplete_year(tmp_path, make_post) -> None:
    connection = connect(tmp_path / "test.sqlite3")
    sync_range(
        connection,
        Client([make_post("1")]),
        start=date(2026, 6, 1),
        end=date(2026, 7, 1),
    )
    with pytest.raises(ValueError, match="incomplete sync coverage"):
        analyze(connection, year=2026, output_dir=tmp_path / "report")


def test_taxonomy_avoids_generic_software_terms() -> None:
    matches = Taxonomy.load().classify(
        {
            "name": "Conventional SaaS",
            "tagline": "A growth API and backend framework",
            "description": "An assistant for e-commerce teams",
            "topics": [],
        }
    )
    assert matches == {}


def test_taxonomy_classifies_vokal_launch_copy() -> None:
    matches = Taxonomy.load().classify(
        {
            "name": "Vokal",
            "tagline": "A collaboration space for 10x teammates with their Al agents",
            "description": (
                "Vokal brings 10x teammates and their agents into one live workspace. "
                "Name your agents, give them roles, and work in a shared collaboration space."
            ),
            "topics": [],
        }
    )
    assert "agent_identity" in matches
    assert "ai_coworkers" in matches
    assert "human_agent_organization" in matches
