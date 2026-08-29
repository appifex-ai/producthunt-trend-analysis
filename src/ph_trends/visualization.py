from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True)
class IndustryEvolution:
    months: tuple[str, ...]
    featured_posts: tuple[int, ...]
    median_votes: tuple[float, ...]
    category_shares: dict[str, tuple[float, ...]]
    category_lifts: dict[str, tuple[float | None, ...]]
    category_posts: dict[str, tuple[int, ...]]
    mcp_shares: tuple[float, ...]
    mcp_posts: tuple[int, ...]


REQUIRED_CATEGORIES = (
    "agent_identity",
    "harness_infrastructure",
    "coding_and_building",
    "openclaw_ecosystem",
    "human_agent_organization",
    "ai_coworkers",
    "gtm_agents",
    "loop_engineering",
)

DISPLAY_LABELS = {
    "agent_identity": "Agent identity",
    "harness_infrastructure": "Harness / infrastructure",
    "mcp_specific": "MCP specifically",
    "coding_and_building": "Coding / building",
    "openclaw_ecosystem": "OpenClaw ecosystem",
    "human_agent_organization": "Human-agent organization",
    "ai_coworkers": "AI coworkers",
    "gtm_agents": "GTM agents",
    "loop_engineering": "Loop engineering",
}

DISPLAY_ROWS = (
    "agent_identity",
    "harness_infrastructure",
    "mcp_specific",
    "coding_and_building",
    "openclaw_ecosystem",
    "human_agent_organization",
    "ai_coworkers",
    "gtm_agents",
    "loop_engineering",
)


def load_industry_evolution(
    category_trends: str | Path,
    monthly_summary: str | Path,
    category_matches: str | Path,
) -> IndustryEvolution:
    monthly_rows = _read_csv(monthly_summary)
    trend_rows = _read_csv(category_trends)
    match_rows = _read_csv(category_matches)
    if not monthly_rows:
        raise ValueError(f"no monthly rows found in {monthly_summary}")

    monthly_rows.sort(key=lambda row: row["month"])
    months = tuple(row["month"] for row in monthly_rows)
    totals = {row["month"]: int(row["featured_posts"]) for row in monthly_rows}
    category_shares: dict[str, tuple[float, ...]] = {}
    category_lifts: dict[str, tuple[float | None, ...]] = {}
    category_posts: dict[str, tuple[int, ...]] = {}

    for category in REQUIRED_CATEGORIES:
        selected = sorted(
            (row for row in trend_rows if row["category"] == category),
            key=lambda row: row["month"],
        )
        selected_months = tuple(row["month"] for row in selected)
        if selected_months != months:
            raise ValueError(f"category {category!r} has inconsistent monthly coverage")
        category_shares[category] = tuple(float(row["population_share"]) for row in selected)
        category_lifts[category] = tuple(
            float(row["top_decile_lift"])
            if row["top_decile_lift"] not in ("", None)
            else None
            for row in selected
        )
        category_posts[category] = tuple(int(row["posts"]) for row in selected)

    mcp_products: dict[str, set[str]] = {month: set() for month in months}
    for row in match_rows:
        if row["month"] not in mcp_products or row["category"] != "harness_infrastructure":
            continue
        terms = {term.strip().lower() for term in row["matched_terms"].split("|")}
        if "mcp" in terms:
            mcp_products[row["month"]].add(row.get("url") or row["name"])
    mcp_posts = tuple(len(mcp_products[month]) for month in months)

    return IndustryEvolution(
        months=months,
        featured_posts=tuple(int(row["featured_posts"]) for row in monthly_rows),
        median_votes=tuple(float(row["median_votes"]) for row in monthly_rows),
        category_shares=category_shares,
        category_lifts=category_lifts,
        category_posts=category_posts,
        mcp_shares=tuple(mcp_posts[index] / totals[month] for index, month in enumerate(months)),
        mcp_posts=mcp_posts,
    )


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def render_linkedin_visual(
    category_trends: str | Path,
    monthly_summary: str | Path,
    category_matches: str | Path,
    output: str | Path,
    *,
    population: int = 5_019,
) -> Path:
    try:
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap, Normalize
        from matplotlib.lines import Line2D
        from matplotlib.patches import Rectangle
    except ImportError as exc:
        raise RuntimeError("install visualization support with `uv sync --extra viz`") from exc

    data = load_industry_evolution(category_trends, monthly_summary, category_matches)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    background = "#F7F8FA"
    ink = "#17191E"
    muted = "#66707D"
    rule = "#D8DEE6"
    coral = "#E84D3D"
    blue = "#276FBF"
    teal = "#168477"
    amber = "#B56A12"

    fig = plt.figure(figsize=(10.8, 13.5), dpi=100, facecolor=background)
    canvas = fig.add_axes((0, 0, 1, 1))
    canvas.set_xlim(0, 1)
    canvas.set_ylim(0, 1)
    canvas.axis("off")

    fig.text(
        0.08,
        0.952,
        "What Product Hunt builders shipped,\nmonth by month",
        color=ink,
        fontsize=26,
        fontweight="bold",
        va="top",
        linespacing=1.08,
    )
    fig.text(
        0.08,
        0.862,
        f"{population:,} featured launches  |  Jan 1-Aug 29, 2026  |  Full population",
        color=muted,
        fontsize=11,
        va="top",
    )

    fig.text(0.08, 0.812, "SHARE OF FEATURED LAUNCHES", color=ink, fontsize=10, fontweight="bold")
    fig.text(0.92, 0.812, "categories overlap", color=muted, fontsize=8.5, ha="right")
    canvas.add_line(Line2D([0.08, 0.92], [0.798, 0.798], color=ink, linewidth=1.4))

    grid_left = 0.31
    grid_right = 0.92
    cell_gap = 0.006
    cell_width = (grid_right - grid_left - cell_gap * 7) / 8
    month_x = tuple(grid_left + index * (cell_width + cell_gap) for index in range(8))
    for index, x in enumerate(month_x):
        fig.text(x + cell_width / 2, 0.774, data.months[index][5:], color=ink, fontsize=9.5,
                 fontweight="bold", ha="center")
        fig.text(x + cell_width / 2, 0.754, f"n={data.featured_posts[index]}", color=muted,
                 fontsize=7.7, ha="center")

    heatmap = LinearSegmentedColormap.from_list(
        "launch_share", ("#EEF3F7", "#AFCDE5", "#4F91C9", "#174A78")
    )
    normalize = Normalize(vmin=0, vmax=0.23)
    row_top = 0.724
    row_height = 0.039
    for row_index, category in enumerate(DISPLAY_ROWS):
        y = row_top - row_index * row_height
        fig.text(0.08, y + 0.012, DISPLAY_LABELS[category], color=ink, fontsize=9.2,
                 fontweight="bold", va="center")
        shares = data.mcp_shares if category == "mcp_specific" else data.category_shares[category]
        for month_index, share in enumerate(shares):
            x = month_x[month_index]
            color = heatmap(normalize(share))
            canvas.add_patch(Rectangle((x, y), cell_width, 0.032, facecolor=color,
                                       edgecolor=background, linewidth=0.8))
            label = "0" if share == 0 else f"{share:.1%}"
            fig.text(x + cell_width / 2, y + 0.016, label,
                     color="white" if share >= 0.105 else ink, fontsize=8.2,
                     fontweight="bold", ha="center", va="center")

    fig.text(0.08, 0.382, "INDUSTRY EVENTS ALIGNED TO THE DATA", color=ink, fontsize=10,
             fontweight="bold")
    fig.text(0.92, 0.382, "descriptive, not causal", color=muted, fontsize=8.5, ha="right")
    canvas.add_line(Line2D([0.08, 0.92], [0.368, 0.368], color=ink, linewidth=1.4))

    event_rows = (
        ("JAN 30", "OPENCLAW RELEASE", "0.2% Jan  ->  5.3% Feb  ->  6.1% Mar  ->  0.8% Aug",
         "A sharp ecosystem spike, then contraction.", coral),
        ("MAY 13", "HARNESS PAPER", "4.6% Jan  ->  8.8% May  ->  10.5% Aug",
         "Launch positioning was rising before the term was formalized.", amber),
        ("JUL 28", "MCP SPEC", "4.2% Jan  ->  8.8% Jul  ->  9.0% Aug",
         "Protocol adoption was established before the specification update.", blue),
        ("JUL 17\nAUG 22", "LOOP ENGINEERING", "0 launches Jul  ->  1 Aug  |  5 all year",
         "Industry discourse has not entered Product Hunt launch copy.", teal),
    )
    for index, (date, event, metric, reading, color) in enumerate(event_rows):
        y = 0.335 - index * 0.064
        fig.text(0.08, y, date, color=color, fontsize=8.5, fontweight="bold", va="top")
        fig.text(0.19, y, event, color=ink, fontsize=9.5, fontweight="bold", va="top")
        fig.text(0.46, y, metric, color=color, fontsize=9.2, fontweight="bold", va="top")
        fig.text(0.46, y - 0.024, reading, color=muted, fontsize=8.2, va="top")
        if index < len(event_rows) - 1:
            canvas.add_line(Line2D([0.19, 0.92], [y - 0.050, y - 0.050], color=rule,
                                   linewidth=0.8))

    fig.text(0.08, 0.075, "WHAT THE DATA SUPPORTS", color=teal, fontsize=9,
             fontweight="bold")
    fig.text(
        0.08,
        0.052,
        "Builders chased agents broadly, OpenClaw briefly, and MCP steadily. "
        "Loop engineering is still\na method, not a launch category.",
        color=ink,
        fontsize=9.8,
        fontweight="bold",
        linespacing=1.35,
    )
    fig.text(
        0.08,
        0.020,
        "Featured launches only. Overlapping text taxonomy. Lift = top-decile share / population "
        "share. Timeline alignment is not causation.",
        color=muted,
        fontsize=8.2,
    )
    fig.text(
        0.08,
        0.006,
        "github.com/appifex-ai/producthunt-trend-analysis",
        color=muted,
        fontsize=8.2,
    )

    fig.savefig(output_path, dpi=100, facecolor=background, metadata={"Software": "ph-trends"})
    plt.close(fig)
    _update_manifest(output_path.parent, population=population)
    return output_path


def _update_manifest(output_dir: Path, *, population: int) -> None:
    manifest_path = output_dir / "manifest.json"
    metadata = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {}
    )
    report_files = sorted(
        path for path in output_dir.iterdir() if path.is_file() and path.name != "manifest.json"
    )
    metadata["posts"] = population
    metadata["files"] = {
        path.name: sha256(path.read_bytes()).hexdigest() for path in report_files
    }
    manifest_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render the LinkedIn industry evolution visual")
    parser.add_argument("--input", default="reports/2026/category_trends.csv")
    parser.add_argument("--monthly", default="reports/2026/monthly_summary.csv")
    parser.add_argument("--matches", default="reports/2026/category_matches.csv")
    parser.add_argument("--output", default="reports/2026/linkedin_trend_cycles.png")
    parser.add_argument("--population", type=int, default=5_019)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = render_linkedin_visual(
        args.input,
        args.monthly,
        args.matches,
        args.output,
        population=args.population,
    )
    print(f"Rendered LinkedIn visual: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
