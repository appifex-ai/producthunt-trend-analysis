from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True)
class ThemeSeries:
    key: str
    label: str
    color: str
    shape: str
    months: tuple[str, ...]
    shares: tuple[float, ...]
    lifts: tuple[float | None, ...]
    posts: tuple[int, ...]


THEMES = (
    ("agent_identity", "Agent identity", "#F25549", "NORMALIZATION"),
    (
        "harness_infrastructure",
        "Harness infrastructure",
        "#276FBF",
        "COMPOUNDING",
    ),
    ("openclaw_ecosystem", "OpenClaw ecosystem", "#7959A6", "SPIKE + CONTRACTION"),
    ("ai_coworkers", "AI coworkers", "#168477", "EARLY + ATTENTION-EFFICIENT"),
)


def load_theme_series(path: str | Path) -> list[ThemeSeries]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"no category trend rows found in {path}")

    series = []
    expected_months: tuple[str, ...] | None = None
    for key, label, color, shape in THEMES:
        selected = sorted(
            (row for row in rows if row["category"] == key),
            key=lambda row: row["month"],
        )
        if not selected:
            raise ValueError(f"category {key!r} is missing from {path}")
        months = tuple(row["month"] for row in selected)
        if expected_months is None:
            expected_months = months
        elif months != expected_months:
            raise ValueError(f"category {key!r} has inconsistent monthly coverage")
        series.append(
            ThemeSeries(
                key=key,
                label=label,
                color=color,
                shape=shape,
                months=months,
                shares=tuple(float(row["population_share"]) for row in selected),
                lifts=tuple(
                    float(row["top_decile_lift"])
                    if row["top_decile_lift"] not in ("", None)
                    else None
                    for row in selected
                ),
                posts=tuple(int(row["posts"]) for row in selected),
            )
        )
    return series


def render_linkedin_visual(
    category_trends: str | Path,
    output: str | Path,
    *,
    population: int = 5_019,
) -> Path:
    try:
        import matplotlib.pyplot as plt
        from matplotlib.ticker import PercentFormatter
    except ImportError as exc:
        raise RuntimeError("install visualization support with `uv sync --extra viz`") from exc

    series = load_theme_series(category_trends)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    background = "#F7F8FA"
    ink = "#181A1F"
    muted = "#68707C"
    grid = "#D9DEE5"
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100, facecolor=background)
    layout = fig.add_gridspec(
        4,
        1,
        left=0.10,
        right=0.92,
        top=0.76,
        bottom=0.13,
        hspace=0.58,
    )

    fig.text(
        0.10,
        0.942,
        "AI agents did not move as one trend",
        color=ink,
        fontsize=27,
        fontweight="bold",
        va="top",
    )
    fig.text(
        0.10,
        0.892,
        "Four adoption curves across 5,019 featured Product Hunt launches in 2026",
        color=muted,
        fontsize=13,
        va="top",
    )
    fig.text(
        0.10,
        0.852,
        "Share of monthly launches matching each narrative",
        color=ink,
        fontsize=11,
        fontweight="bold",
        va="top",
    )

    for index, item in enumerate(series):
        ax = fig.add_subplot(layout[index])
        x = list(range(len(item.months)))
        values = [share * 100 for share in item.shares]
        upper = max(2.0, max(values) * 1.28)
        ax.plot(
            x,
            values,
            color=item.color,
            linewidth=3.0,
            marker="o",
            markersize=5.5,
            markerfacecolor=background,
            markeredgewidth=2.0,
            zorder=3,
        )
        ax.fill_between(x, values, color=item.color, alpha=0.09, zorder=1)
        ax.set_xlim(-0.15, len(x) - 0.65)
        ax.set_ylim(0, upper)
        ax.set_yticks([0, upper / 2, upper])
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
        ax.grid(axis="y", color=grid, linewidth=0.8)
        ax.tick_params(axis="both", colors=muted, labelsize=9, length=0, pad=7)
        for spine in ax.spines.values():
            spine.set_visible(False)

        month_labels = [month[5:] for month in item.months]
        ax.set_xticks(x, month_labels if index == len(series) - 1 else [""] * len(x))
        if index == len(series) - 1:
            ax.set_xlabel("2026 month", color=muted, fontsize=9, labelpad=8)

        latest_lift = item.lifts[-1]
        metric = f"{values[-1]:.1f}% in Aug"
        if latest_lift is not None:
            metric += f"  |  {latest_lift:.2f}x top-decile lift"
        ax.text(
            0,
            1.25,
            item.label,
            transform=ax.transAxes,
            color=ink,
            fontsize=13,
            fontweight="bold",
            va="bottom",
        )
        ax.text(
            1,
            1.25,
            item.shape,
            transform=ax.transAxes,
            color=item.color,
            fontsize=9,
            fontweight="bold",
            ha="right",
            va="bottom",
        )
        ax.text(
            1,
            1.03,
            metric,
            transform=ax.transAxes,
            color=muted,
            fontsize=9,
            ha="right",
            va="bottom",
        )
        peak_index = max(range(len(values)), key=values.__getitem__)
        if peak_index != len(values) - 1:
            ax.annotate(
                f"peak {values[peak_index]:.1f}%",
                xy=(peak_index, values[peak_index]),
                xytext=(0, 12),
                textcoords="offset points",
                color=item.color,
                fontsize=8.5,
                fontweight="bold",
                ha="center",
            )

    fig.text(
        0.10,
        0.075,
        "Jan 1-Aug 29, 2026  |  Featured launches only  |  Categories overlap",
        color=ink,
        fontsize=9.5,
        fontweight="bold",
    )
    fig.text(
        0.10,
        0.049,
        "Text-match taxonomy over launch copy. Lift compares top-decile share with population "
        "share; association, not causation.",
        color=muted,
        fontsize=8.5,
    )
    fig.text(
        0.10,
        0.025,
        "github.com/appifex-ai/producthunt-trend-analysis",
        color=muted,
        fontsize=8.5,
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
    parser = argparse.ArgumentParser(description="Render the LinkedIn trend visualization")
    parser.add_argument("--input", default="reports/2026/category_trends.csv")
    parser.add_argument("--output", default="reports/2026/linkedin_trend_cycles.png")
    parser.add_argument("--population", type=int, default=5_019)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = render_linkedin_visual(args.input, args.output, population=args.population)
    print(f"Rendered LinkedIn visual: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
