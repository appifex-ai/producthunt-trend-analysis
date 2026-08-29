from __future__ import annotations

import argparse
import csv
import json
import textwrap
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
    "openclaw_ecosystem",
    "ai_coworkers",
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
        from matplotlib.lines import Line2D
        from matplotlib.patches import FancyArrowPatch
    except ImportError as exc:
        raise RuntimeError("install visualization support with `uv sync --extra viz`") from exc

    data = load_industry_evolution(category_trends, monthly_summary, category_matches)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    background = "#F7F8FA"
    ink = "#17191E"
    muted = "#66707D"
    rule = "#D8DEE6"
    coral = "#F25549"
    blue = "#276FBF"
    purple = "#7457A6"
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
        "Product Hunt's AI market moved\nfrom labels to infrastructure",
        color=ink,
        fontsize=25,
        fontweight="bold",
        va="top",
        linespacing=1.08,
    )
    fig.text(
        0.08,
        0.862,
        f"{population:,} featured launches  |  Jan 1-Aug 29, 2026  |  Full population",
        color=muted,
        fontsize=11.5,
        va="top",
    )

    fig.text(0.08, 0.814, "THE INDUSTRY SHIFT", color=ink, fontsize=10, fontweight="bold")
    canvas.add_patch(
        FancyArrowPatch(
            (0.08, 0.789),
            (0.92, 0.789),
            arrowstyle="-|>",
            mutation_scale=15,
            linewidth=1.5,
            color=ink,
        )
    )
    shift_labels = (
        (0.10, "AGENT IDENTITY", coral),
        (0.34, "ECOSYSTEMS", purple),
        (0.58, "INTEGRATION", blue),
        (0.80, "ORGANIZATION", teal),
    )
    for x, label, color in shift_labels:
        fig.text(x, 0.768, label, color=color, fontsize=9, fontweight="bold", ha="center")

    columns = (
        (0.08, 0.345, "PAST  |  JAN-MAR", coral),
        (0.38, 0.645, "TRANSITION  |  APR-JUN", amber),
        (0.68, 0.92, "NOW  |  JUL-AUG", blue),
    )
    for left, right, label, color in columns:
        fig.text(left, 0.724, label, color=color, fontsize=9.5, fontweight="bold")
        canvas.add_line(Line2D([left, right], [0.711, 0.711], color=color, linewidth=2.4))
    canvas.add_line(Line2D([0.36, 0.36], [0.49, 0.725], color=rule, linewidth=1))
    canvas.add_line(Line2D([0.66, 0.66], [0.49, 0.725], color=rule, linewidth=1))

    agent = data.category_shares["agent_identity"]
    openclaw = data.category_shares["openclaw_ecosystem"]
    coworker = data.category_shares["ai_coworkers"]
    openclaw_lift = data.category_lifts["openclaw_ecosystem"][-1]
    coworker_lift = data.category_lifts["ai_coworkers"][-1]
    april_supply_change = data.featured_posts[3] / data.featured_posts[2] - 1
    april_vote_change = data.median_votes[3] / data.median_votes[2] - 1
    mcp_harness_share = data.mcp_posts[-1] / data.category_posts["harness_infrastructure"][-1]

    _phase_text(
        fig,
        x=0.08,
        y=0.684,
        headline="A new label\nbecame a market",
        metrics=(
            f"Agent positioning  {agent[0]:.1%} -> {agent[2]:.1%}",
            f"OpenClaw  {openclaw[0]:.1%} -> {openclaw[2]:.1%}",
        ),
        why=(
            "WHY: A named ecosystem gave builders a concrete surface to copy, extend, and package."
        ),
        ink=ink,
        muted=muted,
        accent=coral,
    )
    _phase_text(
        fig,
        x=0.38,
        y=0.684,
        headline="Supply outran\nattention",
        metrics=(
            f"Launches  +{april_supply_change:.0%} Mar -> Apr",
            f"Median votes  {april_vote_change:.0%} Mar -> Apr",
            f"MCP  {data.mcp_shares[3]:.1%} -> {data.mcp_shares[5]:.1%}",
        ),
        why=(
            "WHY: As agent supply crowded in, standardized connections became more valuable than "
            "another wrapper."
        ),
        ink=ink,
        muted=muted,
        accent=amber,
    )
    _phase_text(
        fig,
        x=0.68,
        y=0.684,
        headline="Standards beat\nundifferentiated clones",
        metrics=(
            f"MCP  {data.mcp_shares[-1]:.1%} of Aug launches",
            f"{mcp_harness_share:.0%} of harness matches were MCP",
            f"OpenClaw  {openclaw[-1]:.1%} | {openclaw_lift:.2f}x lift",
            f"Coworker  {coworker[-1]:.1%} | {coworker_lift:.2f}x lift (n=6)",
        ),
        why=(
            "WHY: Attention stayed with differentiated ecosystems and team-level interfaces while "
            "integration became table stakes."
        ),
        ink=ink,
        muted=muted,
        accent=blue,
    )

    fig.text(0.08, 0.445, "WHAT BUILDERS SHOULD DO NEXT", color=ink, fontsize=10, fontweight="bold")
    canvas.add_line(Line2D([0.08, 0.92], [0.431, 0.431], color=ink, linewidth=1.5))

    actions = (
        (
            "01",
            "Do not sell the label",
            f"'Agent' already appears in {agent[-1]:.1%} of August launches. Differentiate on "
            "ownership, outcomes, and failure handling.",
            coral,
        ),
        (
            "02",
            "Build the control plane",
            "MCP explains most infrastructure growth. The next constraints are identity, auth, "
            "permissions, evaluation, memory, and observability.",
            blue,
        ),
        (
            "03",
            "Test the organization layer",
            "Coworker positioning attracts attention but has tiny support. Prototype how humans "
            "delegate, review, and coordinate before scaling the claim.",
            teal,
        ),
    )
    for index, (number, title, body, color) in enumerate(actions):
        top = 0.395 - index * 0.096
        fig.text(0.08, top, number, color=color, fontsize=18, fontweight="bold", va="top")
        fig.text(0.145, top, title, color=ink, fontsize=12.5, fontweight="bold", va="top")
        fig.text(
            0.145,
            top - 0.029,
            body,
            color=muted,
            fontsize=9.5,
            va="top",
            wrap=True,
        )
        if index < len(actions) - 1:
            canvas.add_line(
                Line2D([0.145, 0.92], [top - 0.076, top - 0.076], color=rule, linewidth=0.8)
            )

    fig.text(0.08, 0.105, "PAST", color=coral, fontsize=8.5, fontweight="bold")
    fig.text(0.38, 0.105, "NOW", color=blue, fontsize=8.5, fontweight="bold")
    fig.text(0.67, 0.105, "NEXT  |  INFERENCE", color=teal, fontsize=8.5, fontweight="bold")
    fig.text(0.08, 0.079, "agent identity", color=ink, fontsize=10.5, fontweight="bold")
    fig.text(0.38, 0.079, "interoperable\nsystems", color=ink, fontsize=10.5, fontweight="bold")
    fig.text(
        0.67,
        0.079,
        "trustworthy agent\norganizations",
        color=ink,
        fontsize=10.5,
        fontweight="bold",
    )
    canvas.add_patch(
        FancyArrowPatch(
            (0.21, 0.084),
            (0.35, 0.084),
            arrowstyle="-|>",
            mutation_scale=10,
            linewidth=1,
            color=muted,
        )
    )
    canvas.add_patch(
        FancyArrowPatch(
            (0.53, 0.084),
            (0.64, 0.084),
            arrowstyle="-|>",
            mutation_scale=10,
            linewidth=1,
            color=muted,
        )
    )
    fig.text(
        0.08,
        0.040,
        "Featured launches only. Overlapping text taxonomy. Lift = top-decile share / population "
        "share. Timeline alignment is not causation.",
        color=muted,
        fontsize=8.2,
    )
    fig.text(
        0.08,
        0.019,
        "github.com/appifex-ai/producthunt-trend-analysis",
        color=muted,
        fontsize=8.2,
    )

    fig.savefig(output_path, dpi=100, facecolor=background, metadata={"Software": "ph-trends"})
    plt.close(fig)
    _update_manifest(output_path.parent, population=population)
    return output_path


def _phase_text(
    fig,
    *,
    x: float,
    y: float,
    headline: str,
    metrics: tuple[str, ...],
    why: str,
    ink: str,
    muted: str,
    accent: str,
) -> None:
    fig.text(x, y, headline, color=ink, fontsize=14, fontweight="bold", va="top", linespacing=1.08)
    metric_y = y - 0.075
    for index, metric in enumerate(metrics):
        fig.text(x, metric_y - index * 0.025, metric, color=accent, fontsize=9.5, fontweight="bold")
    fig.text(
        x,
        metric_y - len(metrics) * 0.025 - 0.015,
        textwrap.fill(why, width=38),
        color=muted,
        fontsize=8.5,
        va="top",
        wrap=True,
    )


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
