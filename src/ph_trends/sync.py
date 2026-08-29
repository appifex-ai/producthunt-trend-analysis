from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from ph_trends.api import ProductHuntClient
from ph_trends.db import (
    begin_run,
    fail_window,
    finish_run,
    prepare_window,
    save_page,
)

logger = logging.getLogger(__name__)


def as_api_datetime(value: date) -> str:
    return datetime(value.year, value.month, value.day, tzinfo=UTC).isoformat()


def month_windows(start: date, end: date) -> list[tuple[date, date]]:
    if end <= start:
        raise ValueError("end must be after start")
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor < end:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        window_end = min(end, next_month)
        windows.append((cursor, window_end))
        cursor = window_end
    return windows


@dataclass(frozen=True)
class SyncResult:
    run_id: int
    requests: int
    posts_seen: int
    windows_completed: int


@dataclass(frozen=True)
class VerifyResult:
    requests: int
    windows_verified: int


def sync_range(
    connection: sqlite3.Connection,
    client: ProductHuntClient,
    *,
    start: date,
    end: date,
    refresh: bool = False,
) -> SyncResult:
    range_start = as_api_datetime(start)
    range_end = as_api_datetime(end)
    query_fingerprint = getattr(client, "query_fingerprint", None)
    run_id = begin_run(
        connection,
        range_start,
        range_end,
        api_url=getattr(client, "_api_url", None),
        query_fingerprint=query_fingerprint,
    )
    posts_seen = 0
    windows_completed = 0

    try:
        for window_start_date, window_end_date in month_windows(start, end):
            window_start = as_api_datetime(window_start_date)
            window_end = as_api_datetime(window_end_date)
            mutable_window = window_end_date >= datetime.now(UTC).date() - timedelta(days=7)
            effective_refresh = refresh or mutable_window
            window = prepare_window(
                connection,
                window_start,
                window_end,
                refresh=effective_refresh,
                query_fingerprint=query_fingerprint,
            )
            if window["status"] == "completed" and not effective_refresh:
                windows_completed += 1
                continue

            logger.info("Syncing %s through %s", window_start_date, window_end_date)
            after = window["cursor"]
            api_window_start = window_start
            if window_start_date > start:
                api_window_start = (
                    datetime(
                        window_start_date.year,
                        window_start_date.month,
                        window_start_date.day,
                        tzinfo=UTC,
                    )
                    - timedelta(seconds=1)
                ).isoformat()
            while True:
                try:
                    page = client.fetch_posts_page(
                        start=api_window_start, end=window_end, after=after
                    )
                    completed = not page.has_next_page
                    if page.has_next_page and (not page.end_cursor or page.end_cursor == after):
                        raise RuntimeError("pagination cursor did not advance")
                    posts_seen += save_page(
                        connection,
                        window_id=int(window["id"]),
                        posts=page.posts,
                        next_cursor=page.end_cursor,
                        completed=completed,
                        expected_count=page.total_count,
                    )
                    if completed:
                        windows_completed += 1
                        logger.info("Completed window through %s", window_end_date)
                        break
                    after = page.end_cursor
                except BaseException as exc:
                    fail_window(
                        connection,
                        int(window["id"]),
                        str(exc) or type(exc).__name__,
                    )
                    raise

        finish_run(
            connection,
            run_id,
            status="completed",
            requests_count=client.request_count,
            posts_seen=posts_seen,
            rate_limit=client.rate_limit,
        )
    except BaseException as exc:
        finish_run(
            connection,
            run_id,
            status="failed",
            requests_count=client.request_count,
            posts_seen=posts_seen,
            rate_limit=client.rate_limit,
            error=str(exc) or type(exc).__name__,
        )
        raise

    return SyncResult(
        run_id=run_id,
        requests=client.request_count,
        posts_seen=posts_seen,
        windows_completed=windows_completed,
    )


def verify_range_counts(
    connection: sqlite3.Connection,
    client: ProductHuntClient,
    *,
    start: date,
    end: date,
) -> VerifyResult:
    verified = 0
    for window_start_date, window_end_date in month_windows(start, end):
        window_start = as_api_datetime(window_start_date)
        window_end = as_api_datetime(window_end_date)
        api_window_start = window_start
        if window_start_date > start:
            api_window_start = (
                datetime(
                    window_start_date.year,
                    window_start_date.month,
                    window_start_date.day,
                    tzinfo=UTC,
                )
                - timedelta(seconds=1)
            ).isoformat()
        row = connection.execute(
            "SELECT * FROM sync_windows WHERE range_start = ? AND range_end = ?",
            (window_start, window_end),
        ).fetchone()
        if not row or row["status"] != "completed":
            raise RuntimeError(
                "cannot verify incomplete or missing window "
                f"{window_start_date} to {window_end_date}"
            )
        page = client.fetch_posts_page(start=api_window_start, end=window_end)
        local_count = connection.execute(
            "SELECT COUNT(*) FROM window_posts WHERE window_id = ?", (int(row["id"]),)
        ).fetchone()[0]
        if page.total_count != local_count:
            raise RuntimeError(
                f"window count mismatch for {window_start_date}: "
                f"API reported {page.total_count}, collected {local_count}"
            )
        connection.execute(
            "UPDATE sync_windows SET expected_count = ?, updated_at = ? WHERE id = ?",
            (page.total_count, datetime.now(UTC).isoformat(), int(row["id"])),
        )
        connection.commit()
        verified += 1
    return VerifyResult(requests=client.request_count, windows_verified=verified)
