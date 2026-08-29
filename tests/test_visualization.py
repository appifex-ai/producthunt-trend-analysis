from __future__ import annotations

import csv

import pytest

from ph_trends.visualization import THEMES, load_theme_series


def test_load_theme_series_reads_consistent_months(tmp_path) -> None:
    path = tmp_path / "category_trends.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "month",
                "category",
                "label",
                "posts",
                "population_share",
                "top_decile_lift",
            ],
        )
        writer.writeheader()
        for key, label, _, _ in THEMES:
            writer.writerow(
                {
                    "month": "2026-01",
                    "category": key,
                    "label": label,
                    "posts": 2,
                    "population_share": 0.1,
                    "top_decile_lift": "",
                }
            )
            writer.writerow(
                {
                    "month": "2026-02",
                    "category": key,
                    "label": label,
                    "posts": 3,
                    "population_share": 0.2,
                    "top_decile_lift": 1.5,
                }
            )

    series = load_theme_series(path)

    assert [item.key for item in series] == [theme[0] for theme in THEMES]
    assert series[0].months == ("2026-01", "2026-02")
    assert series[0].shares == (0.1, 0.2)
    assert series[0].lifts == (None, 1.5)


def test_load_theme_series_rejects_missing_category(tmp_path) -> None:
    path = tmp_path / "category_trends.csv"
    path.write_text(
        "month,category,label,posts,population_share,top_decile_lift\n"
        "2026-01,agent_identity,Agent identity,2,0.1,1.2\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="harness_infrastructure"):
        load_theme_series(path)
