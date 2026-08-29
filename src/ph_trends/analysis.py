from __future__ import annotations

import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from typing import Any

from ph_trends.taxonomy import Taxonomy


@dataclass(frozen=True)
class AnalysisResult:
    year: int
    posts: int
    months: int
    output_dir: Path


def load_posts(connection: sqlite3.Connection, year: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT p.*, GROUP_CONCAT(t.name, ' | ') AS topic_names
        FROM posts p
        LEFT JOIN post_topics pt ON pt.post_id = p.product_hunt_id
        LEFT JOIN topics t ON t.product_hunt_id = pt.topic_id
        WHERE p.featured_at >= ? AND p.featured_at < ? AND p.is_active = 1
        GROUP BY p.product_hunt_id
        ORDER BY p.featured_at, p.product_hunt_id
        """,
        (f"{year:04d}-01-01", f"{year + 1:04d}-01-01"),
    ).fetchall()
    return [
        {
            **dict(row),
            "topics": (row["topic_names"] or "").split(" | ") if row["topic_names"] else [],
        }
        for row in rows
    ]


def _month(post: dict[str, Any]) -> str:
    return str(post["featured_at"])[:7]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def analyze(
    connection: sqlite3.Connection,
    *,
    year: int,
    output_dir: str | Path,
    taxonomy: Taxonomy | None = None,
    allow_partial: bool = False,
) -> AnalysisResult:
    taxonomy = taxonomy or Taxonomy.load()
    if not allow_partial:
        validate_coverage(connection, year)
    posts = load_posts(connection, year)
    if not posts:
        raise ValueError(f"no featured posts found for {year}")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for post in posts:
        post["category_matches"] = taxonomy.classify(post)
        by_month[_month(post)].append(post)

    monthly_rows: list[dict[str, Any]] = []
    category_rows: list[dict[str, Any]] = []
    top_rows: list[dict[str, Any]] = []
    match_rows: list[dict[str, Any]] = []
    previous_shares: dict[str, float] = {}

    for month, month_posts in sorted(by_month.items()):
        ranked = sorted(
            month_posts,
            key=lambda post: (-int(post["votes_count"]), str(post["name"]).lower()),
        )
        target_top_count = max(1, math.ceil(len(ranked) * 0.10))
        vote_cutoff = int(ranked[target_top_count - 1]["votes_count"])
        top_decile = [post for post in ranked if int(post["votes_count"]) >= vote_cutoff]
        top_count = len(top_decile)
        ranks = {post["product_hunt_id"]: rank for rank, post in enumerate(ranked, start=1)}
        monthly_rows.append(
            {
                "month": month,
                "featured_posts": len(ranked),
                "total_votes": sum(int(post["votes_count"]) for post in ranked),
                "median_votes": _median([int(post["votes_count"]) for post in ranked]),
                "top_decile_size": top_count,
                "classified_posts": sum(bool(post["category_matches"]) for post in ranked),
                "multi_label_posts": sum(len(post["category_matches"]) > 1 for post in ranked),
            }
        )

        for rank, post in enumerate(ranked[:25], start=1):
            top_rows.append(
                {
                    "month": month,
                    "rank": rank,
                    "name": post["name"],
                    "votes": post["votes_count"],
                    "comments": post["comments_count"],
                    "url": post["product_hunt_url"],
                    "categories": " | ".join(post["category_matches"]),
                }
            )

        for category in taxonomy.categories:
            all_matches = [post for post in ranked if category.key in post["category_matches"]]
            top_matches = [post for post in top_decile if category.key in post["category_matches"]]
            population_share = len(all_matches) / len(ranked)
            top_share = len(top_matches) / top_count
            ci_low, ci_high = _wilson_interval(len(all_matches), len(ranked))
            previous = previous_shares.get(category.key)
            category_rows.append(
                {
                    "month": month,
                    "category": category.key,
                    "label": category.label,
                    "posts": len(all_matches),
                    "population_share": round(population_share, 6),
                    "population_ci_low": round(ci_low, 6),
                    "population_ci_high": round(ci_high, 6),
                    "top_decile_posts": len(top_matches),
                    "top_decile_share": round(top_share, 6),
                    "top_decile_lift": (
                        round(top_share / population_share, 3) if population_share else ""
                    ),
                    "share_change_pp": (
                        round((population_share - previous) * 100, 2)
                        if previous is not None
                        else ""
                    ),
                }
            )
            previous_shares[category.key] = population_share
            for post in all_matches:
                match_rows.append(
                    {
                        "month": month,
                        "category": category.key,
                        "name": post["name"],
                        "monthly_rank": ranks[post["product_hunt_id"]],
                        "votes": post["votes_count"],
                        "matched_terms": " | ".join(post["category_matches"][category.key]),
                        "url": post["product_hunt_url"],
                    }
                )

    _write_csv(
        output / "monthly_summary.csv",
        [
            "month",
            "featured_posts",
            "total_votes",
            "median_votes",
            "top_decile_size",
            "classified_posts",
            "multi_label_posts",
        ],
        monthly_rows,
    )
    _write_csv(
        output / "category_trends.csv",
        [
            "month",
            "category",
            "label",
            "posts",
            "population_share",
            "population_ci_low",
            "population_ci_high",
            "top_decile_posts",
            "top_decile_share",
            "top_decile_lift",
            "share_change_pp",
        ],
        category_rows,
    )
    _write_csv(
        output / "top_products.csv",
        ["month", "rank", "name", "votes", "comments", "url", "categories"],
        top_rows,
    )
    _write_csv(
        output / "category_matches.csv",
        ["month", "category", "name", "monthly_rank", "votes", "matched_terms", "url"],
        match_rows,
    )
    timeline_rows = _theme_timelines(category_rows)
    events = _load_external_events(year)
    _write_csv(
        output / "theme_timelines.csv",
        [
            "category",
            "label",
            "first_observed_month",
            "peak_share_month",
            "peak_population_share",
            "peak_lift_month",
            "peak_top_decile_lift",
            "latest_month",
            "latest_population_share",
            "first_to_latest_change_pp",
        ],
        timeline_rows,
    )
    _write_csv(
        output / "external_events.csv",
        ["date", "theme", "event", "source"],
        events,
    )
    (output / "report.md").write_text(
        _render_report(
            year,
            posts,
            monthly_rows,
            category_rows,
            timeline_rows,
            events,
            taxonomy.version,
        ),
        encoding="utf-8",
    )
    (output / "analysis.json").write_text(
        json.dumps(
            {
                "year": year,
                "taxonomy_version": taxonomy.version,
                "posts": len(posts),
                "monthly_summary": monthly_rows,
                "category_trends": category_rows,
                "theme_timelines": timeline_rows,
                "external_events": events,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    report_files = sorted(
        path for path in output.iterdir() if path.is_file() and path.name != "manifest.json"
    )
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "year": year,
                "taxonomy_version": taxonomy.version,
                "posts": len(posts),
                "files": {
                    path.name: sha256(path.read_bytes()).hexdigest() for path in report_files
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return AnalysisResult(year=year, posts=len(posts), months=len(by_month), output_dir=output)


def validate_coverage(connection: sqlite3.Connection, year: int) -> None:
    start = date(year, 1, 1)
    end = min(date(year + 1, 1, 1), datetime.now(UTC).date() + timedelta(days=1))
    rows = connection.execute(
        """
        SELECT range_start, range_end FROM sync_windows
        WHERE status = 'completed' AND range_end > ? AND range_start < ?
        ORDER BY range_start, range_end
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    intervals = [
        (
            datetime.fromisoformat(row["range_start"].replace("Z", "+00:00")).date(),
            datetime.fromisoformat(row["range_end"].replace("Z", "+00:00")).date(),
        )
        for row in rows
    ]
    cursor = start
    while cursor < end:
        covering = [
            interval_end for interval_start, interval_end in intervals if interval_start <= cursor
        ]
        next_cursor = max(covering, default=cursor)
        if next_cursor <= cursor:
            raise ValueError(
                f"incomplete sync coverage for {year}: no completed window covers {cursor}; "
                "finish sync or pass --allow-partial"
            )
        cursor = next_cursor


def _median(values: list[int]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def _load_external_events(year: int) -> list[dict[str, str]]:
    resource = files("ph_trends").joinpath(f"external_events_{year}.json")
    if not resource.is_file():
        return []
    return json.loads(resource.read_text(encoding="utf-8"))


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    proportion = successes / total
    denominator = 1 + z**2 / total
    center = (proportion + z**2 / (2 * total)) / denominator
    margin = (
        z * math.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2)) / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _theme_timelines(category_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in category_rows:
        grouped[row["category"]].append(row)
    timelines = []
    for category, rows in grouped.items():
        rows.sort(key=lambda row: row["month"])
        seen = [row for row in rows if row["posts"]]
        if not seen:
            continue
        peak_share = max(seen, key=lambda row: (float(row["population_share"]), row["month"]))
        with_lift = [row for row in seen if row["top_decile_lift"] != "" and row["posts"] >= 3]
        peak_lift = (
            max(
                with_lift,
                key=lambda row: (float(row["top_decile_lift"]), row["month"]),
            )
            if with_lift
            else None
        )
        first = seen[0]
        latest = rows[-1]
        timelines.append(
            {
                "category": category,
                "label": first["label"],
                "first_observed_month": first["month"],
                "peak_share_month": peak_share["month"],
                "peak_population_share": peak_share["population_share"],
                "peak_lift_month": peak_lift["month"] if peak_lift else "",
                "peak_top_decile_lift": peak_lift["top_decile_lift"] if peak_lift else "",
                "latest_month": latest["month"],
                "latest_population_share": latest["population_share"],
                "first_to_latest_change_pp": round(
                    (float(latest["population_share"]) - float(first["population_share"])) * 100,
                    2,
                ),
            }
        )
    return sorted(timelines, key=lambda row: row["category"])


def _render_report(
    year: int,
    posts: list[dict[str, Any]],
    monthly_rows: list[dict[str, Any]],
    category_rows: list[dict[str, Any]],
    timeline_rows: list[dict[str, Any]],
    events: list[dict[str, str]],
    taxonomy_version: str,
) -> str:
    latest_month = monthly_rows[-1]["month"]
    snapshot_at = max(str(post["last_seen_at"]) for post in posts)
    aggregate = Counter()
    for post in posts:
        aggregate.update(post["category_matches"].keys())
    strongest = sorted(aggregate.items(), key=lambda item: (-item[1], item[0]))
    latest = [row for row in category_rows if row["month"] == latest_month and row["posts"]]
    latest.sort(key=lambda row: (-float(row["population_share"]), row["category"]))
    lines = [
        f"# Product Hunt {year} trend analysis",
        "",
        f"Analyzed **{len(posts):,} featured products** across **{len(monthly_rows)} months**.",
        "This report uses the full collected population, not a monthly top-N sample.",
        f"Vote and comment counts are cumulative snapshots collected through `{snapshot_at}`.",
        "",
        "## Dataset",
        "",
        "| Month | Featured products | Median votes | Total votes |",
        "|---|---:|---:|---:|",
    ]
    lines.extend(
        f"| {row['month']} | {row['featured_posts']:,} | {row['median_votes']:g} | "
        f"{row['total_votes']:,} |"
        for row in monthly_rows
    )
    lines.extend(["", f"## Most common themes through {latest_month}", ""])
    for key, count in strongest:
        lines.append(f"- **{key.replace('_', ' ').title()}**: {count:,} products")
    lines.extend(["", f"## Latest month ({latest_month})", ""])
    for row in latest:
        lift = row["top_decile_lift"]
        lift_text = f", {lift}x top-decile lift" if lift != "" else ""
        lines.append(
            f"- **{row['label']}**: {row['posts']}/{monthly_rows[-1]['featured_posts']} "
            f"launches ({float(row['population_share']):.1%}); "
            f"{row['top_decile_posts']}/{monthly_rows[-1]['top_decile_size']} in the top decile"
            f"{lift_text}"
        )
    lines.extend(["", "## Theme timelines", ""])
    lines.extend(
        [
            "| Theme | First observed | Peak share | Peak lift | Latest share | Net change |",
            "|---|---|---|---|---:|---:|",
        ]
    )
    for row in timeline_rows:
        peak_lift = (
            f"{row['peak_lift_month']} ({row['peak_top_decile_lift']}x)"
            if row["peak_lift_month"]
            else "insufficient support"
        )
        lines.append(
            f"| {row['label']} | {row['first_observed_month']} | {row['peak_share_month']} "
            f"({float(row['peak_population_share']):.1%}) | {peak_lift} | "
            f"{float(row['latest_population_share']):.1%} | "
            f"{float(row['first_to_latest_change_pp']):+.1f} pp |"
        )
    if events:
        lines.extend(["", "## External timeline anchors", ""])
        for event in events:
            lines.append(f"- **{event['date']}**: {event['event']} ([source]({event['source']}))")
    lines.extend(
        [
            "",
            "## Methodology",
            "",
            "Posts are fetched from Product Hunt's GraphQL API with `featured: true`, "
            "partitioned into bounded monthly windows, and fully paginated. Categories are "
            "multi-label regex matches over name, tagline, description, and available topics. "
            "The top decile is recomputed independently for each month by current vote count.",
            "Categories overlap because a launch may match multiple narratives. Top-decile lift "
            "measures representation among high-vote launches; it does not establish causation or "
            "equal-age launch performance.",
            "",
            f"Taxonomy version: `{taxonomy_version}`.",
            "",
        ]
    )
    return "\n".join(lines)


def find_products(
    connection: sqlite3.Connection, query: str, *, limit: int = 20
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        WITH ranked AS (
          SELECT p.*,
                 substr(featured_at, 1, 7) AS month,
                 RANK() OVER (
                   PARTITION BY substr(featured_at, 1, 7)
                   ORDER BY votes_count DESC
                 ) AS month_rank,
                 COUNT(*) OVER (PARTITION BY substr(featured_at, 1, 7)) AS month_count
          FROM posts p
          WHERE featured_at IS NOT NULL
        )
        SELECT * FROM ranked
        WHERE name LIKE ? COLLATE NOCASE OR slug LIKE ? COLLATE NOCASE
        ORDER BY featured_at DESC
        LIMIT ?
        """,
        (f"%{query}%", f"%{query}%", limit),
    ).fetchall()
    return [
        {
            **dict(row),
            "percentile": round(
                (
                    (int(row["month_count"]) - int(row["month_rank"]))
                    / max(1, int(row["month_count"]) - 1)
                )
                * 100,
                1,
            ),
        }
        for row in rows
    ]
