# Product Hunt Trend Analysis

A reproducible pipeline that collects every featured Product Hunt launch in a date range,
stores it in SQLite, and measures which product themes are growing and overrepresented among
each month's top decile.

The project was created to replace fragile "top 17 per month" analysis. A top-N sample omitted
Vokal even though it launched on June 2, 2026 and ranked #2 that day. This pipeline analyzes the
full collected population and can report any product's rank within its launch month.

## Setup

Create a Product Hunt developer application and obtain a developer token. Keep the token outside
the repository.

```bash
python3.12 -m venv .venv
. .venv/bin/activate
uv sync --all-extras --locked
export PRODUCT_HUNT_TOKEN='your-token'
ph-trends init
```

The default database is `data/producthunt.sqlite3`. Override it with `--db` or `PH_TRENDS_DB`.

## Collect and analyze

Backfill a bounded range, using an exclusive end date:

```bash
ph-trends sync --start 2026-01-01 --end 2027-01-01
ph-trends analyze --year 2026 --output reports/2026
ph-trends product Vokal
```

For future runs, omit the dates. The collector resumes seven days before the newest stored post so
late vote-count changes are refreshed while old completed windows remain untouched.

```bash
ph-trends sync
ph-trends status
```

Use `--refresh` to deliberately replay all requested windows. Run `scripts/run_2026.sh` for the
complete 2026 workflow.

Analysis refuses to label an incomplete date range as a full population. Use `--allow-partial`
only for deliberate exploratory work while a backfill is still running.

## Storage and reliability

- SQLite uses WAL mode, foreign keys, atomic page writes, and idempotent post/topic upserts.
- `sync_windows` stores a cursor after every successful page, so an interrupted backfill resumes
  from the last committed page.
- Date ranges are split into monthly windows to bound retries and make incremental refreshes cheap.
- The API client reads Product Hunt rate-limit headers, keeps a configurable reserve, waits for
  reset, honors HTTP 429, and retries transient network/5xx failures with exponential backoff.
- Raw Product Hunt JSON is preserved alongside normalized post tables for re-analysis. The schema
  can retain topic edges when a future targeted enrichment query supplies them.
- No token or OAuth secret is written to SQLite, reports, logs, or version control.

The CLI enforces one sync writer per database. For parallel backfills, use separate SQLite files and
merge only after all workers finish, or move the schema to PostgreSQL with explicit worker leases.
SQLite is appropriate for this local analytics workload; concurrent writers require a different
coordination model.

## Outputs

`ph-trends analyze` writes deterministic files:

- `monthly_summary.csv`: full monthly population, votes, and top-decile size
- `category_trends.csv`: monthly prevalence, month-over-month change, and top-decile lift
- `theme_timelines.csv`: first appearance, peak months, latest share, and net change by theme
- `top_products.csv`: top 25 launches per month for inspection
- `category_matches.csv`: every matched product and term for manual false-positive review
- `external_events.csv`: versioned primary-source milestones for descriptive timeline comparison
- `analysis.json`: machine-readable results with taxonomy version
- `report.md`: concise human-readable summary and methodology
- `manifest.json`: SHA-256 checksums for reproducibility and change review

Categories are multi-label rules in `src/ph_trends/taxonomy.json`. They match names, taglines,
descriptions, and any stored Product Hunt topics. The full-population collector intentionally avoids
nested topic requests because they consume disproportionate GraphQL complexity. Rules are versioned
and auditable; edit the taxonomy and rerun analysis without calling the API again.
Monthly prevalence includes Wilson 95% intervals. Timeline peak-lift claims require at least three
matched launches in a month; lower-support rows remain available in the audit CSV.

## Methodology limits

The API is queried with `featured: true`, so this is an analysis of featured Product Hunt launches,
not every submitted product. Vote and comment counts are snapshots at collection time and may
change. Keyword taxonomy shows narrative positioning, not causal intent. Top-decile lift indicates
overrepresentation among high-vote launches; it does not prove that a theme caused performance.

## Development

```bash
ruff check .
pytest
```

CI runs both checks on Python 3.12 and 3.13 without live API credentials.
`uv.lock` pins the exact dependency resolution used by local and CI reproduction.
