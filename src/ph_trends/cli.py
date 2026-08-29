from __future__ import annotations

import argparse
import fcntl
import logging
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ph_trends.analysis import analyze, find_products
from ph_trends.api import ProductHuntClient
from ph_trends.config import DEFAULT_DB_PATH, Settings
from ph_trends.db import connect
from ph_trends.sync import sync_range
from ph_trends.taxonomy import Taxonomy


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def _db_path(value: str | None) -> Path:
    return Path(value or os.environ.get("PH_TRENDS_DB", DEFAULT_DB_PATH))


def _default_start(connection: sqlite3.Connection) -> date:
    row = connection.execute("SELECT MAX(featured_at) AS latest FROM posts").fetchone()
    if row and row["latest"]:
        return datetime.fromisoformat(row["latest"].replace("Z", "+00:00")).date() - timedelta(
            days=7
        )
    return date(datetime.now(UTC).year, 1, 1)


@contextmanager
def _exclusive_sync_lock(db_path: Path):
    lock_path = db_path.with_suffix(db_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"another sync process holds {lock_path}") from exc
        yield


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Product Hunt ingestion and trend analysis")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="initialize or migrate the SQLite database")
    init.add_argument("--db")

    sync = subparsers.add_parser("sync", help="incrementally fetch featured Product Hunt posts")
    sync.add_argument("--db")
    sync.add_argument("--start", type=_date)
    sync.add_argument("--end", type=_date)
    sync.add_argument("--refresh", action="store_true")
    sync.add_argument("--page-delay", type=float)
    sync.add_argument("--rate-reserve", type=int)

    analysis = subparsers.add_parser("analyze", help="write deterministic analysis exports")
    analysis.add_argument("--db")
    analysis.add_argument("--year", type=int, required=True)
    analysis.add_argument("--output")
    analysis.add_argument("--taxonomy")
    analysis.add_argument("--allow-partial", action="store_true")

    product = subparsers.add_parser("product", help="find products and monthly vote rank")
    product.add_argument("query")
    product.add_argument("--db")

    status = subparsers.add_parser("status", help="show warehouse and last-run status")
    status.add_argument("--db")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = build_parser().parse_args(argv)
    db_path = _db_path(getattr(args, "db", None))
    try:
        connection = connect(db_path)
        if args.command == "init":
            print(f"Initialized SQLite warehouse: {db_path}")
        elif args.command == "sync":
            settings = Settings.from_env(
                db_path=db_path,
                page_delay_seconds=args.page_delay,
                rate_limit_reserve=args.rate_reserve,
            )
            start = args.start or _default_start(connection)
            end = args.end or (datetime.now(UTC).date() + timedelta(days=1))
            with _exclusive_sync_lock(db_path):
                with ProductHuntClient(
                    token=settings.token,
                    api_url=settings.api_url,
                    page_size=settings.page_size,
                    page_delay_seconds=settings.page_delay_seconds,
                    rate_limit_reserve=settings.rate_limit_reserve,
                    max_retries=settings.max_retries,
                ) as client:
                    result = sync_range(
                        connection, client, start=start, end=end, refresh=args.refresh
                    )
            print(
                f"Sync complete: {result.posts_seen:,} posts across "
                f"{result.windows_completed} windows in {result.requests} requests"
            )
        elif args.command == "analyze":
            output = Path(args.output or f"reports/{args.year}")
            taxonomy = Taxonomy.load(args.taxonomy)
            result = analyze(
                connection,
                year=args.year,
                output_dir=output,
                taxonomy=taxonomy,
                allow_partial=args.allow_partial,
            )
            print(
                f"Analysis complete: {result.posts:,} posts across {result.months} months; "
                f"wrote {result.output_dir}"
            )
        elif args.command == "product":
            matches = find_products(connection, args.query)
            if not matches:
                print(f"No products matched {args.query!r}")
                return 1
            for post in matches:
                print(
                    f"{post['name']} | {post['featured_at'][:10]} | "
                    f"{post['votes_count']} votes | #{post['month_rank']} of "
                    f"{post['month_count']} ({post['percentile']}th percentile) | "
                    f"{post['product_hunt_url']}"
                )
        elif args.command == "status":
            _print_status(connection, db_path)
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        if "connection" in locals():
            connection.close()


def _print_status(connection: sqlite3.Connection, db_path: Path) -> None:
    posts = connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    earliest, latest = connection.execute(
        "SELECT MIN(featured_at), MAX(featured_at) FROM posts"
    ).fetchone()
    run = connection.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
    print(f"Database: {db_path}")
    print(f"Posts: {posts:,}; featured range: {earliest or '-'} to {latest or '-'}")
    if run:
        print(
            f"Last sync: {run['status']} at {run['started_at']}; "
            f"{run['requests_count']} requests, {run['posts_seen']} posts seen"
        )
    active = connection.execute(
        """
        SELECT range_start, range_end, status, pages_fetched, posts_seen, expected_count
        FROM sync_windows WHERE status IN ('running', 'failed')
        ORDER BY updated_at DESC LIMIT 1
        """
    ).fetchone()
    if active:
        print(
            f"Window: {active['range_start'][:10]} to {active['range_end'][:10]} "
            f"is {active['status']}; {active['pages_fetched']} pages, "
            f"{active['posts_seen']} rows, expected {active['expected_count'] or '?'}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
