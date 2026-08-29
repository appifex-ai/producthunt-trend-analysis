from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def connect(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    migrate(connection)
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
            range_start TEXT NOT NULL,
            range_end TEXT NOT NULL,
            requests_count INTEGER NOT NULL DEFAULT 0,
            posts_seen INTEGER NOT NULL DEFAULT 0,
            rate_limit_limit INTEGER,
            rate_limit_remaining INTEGER,
            rate_limit_reset TEXT,
            api_url TEXT,
            query_fingerprint TEXT,
            collector_version TEXT,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS sync_windows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            range_start TEXT NOT NULL,
            range_end TEXT NOT NULL,
            cursor TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'completed', 'failed')),
            pages_fetched INTEGER NOT NULL DEFAULT 0,
            posts_seen INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            expected_count INTEGER,
            query_fingerprint TEXT,
            last_error TEXT,
            UNIQUE(range_start, range_end)
        );

        CREATE TABLE IF NOT EXISTS posts (
            product_hunt_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            tagline TEXT NOT NULL,
            description TEXT,
            product_hunt_url TEXT NOT NULL,
            website_url TEXT,
            votes_count INTEGER NOT NULL,
            comments_count INTEGER NOT NULL,
            reviews_count INTEGER NOT NULL DEFAULT 0,
            reviews_rating REAL NOT NULL DEFAULT 0,
            featured_at TEXT,
            created_at TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_posts_featured_at ON posts(featured_at);
        CREATE INDEX IF NOT EXISTS idx_posts_votes ON posts(votes_count DESC);
        CREATE INDEX IF NOT EXISTS idx_posts_slug ON posts(slug);
        CREATE INDEX IF NOT EXISTS idx_posts_name ON posts(name COLLATE NOCASE);

        CREATE TABLE IF NOT EXISTS topics (
            product_hunt_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS post_topics (
            post_id TEXT NOT NULL REFERENCES posts(product_hunt_id) ON DELETE CASCADE,
            topic_id TEXT NOT NULL REFERENCES topics(product_hunt_id) ON DELETE CASCADE,
            PRIMARY KEY(post_id, topic_id)
        );

        CREATE TABLE IF NOT EXISTS window_posts (
            window_id INTEGER NOT NULL REFERENCES sync_windows(id) ON DELETE CASCADE,
            post_id TEXT NOT NULL REFERENCES posts(product_hunt_id) ON DELETE CASCADE,
            PRIMARY KEY(window_id, post_id)
        );

        CREATE TABLE IF NOT EXISTS post_metrics_snapshots (
            post_id TEXT NOT NULL REFERENCES posts(product_hunt_id) ON DELETE CASCADE,
            captured_at TEXT NOT NULL,
            votes_count INTEGER NOT NULL,
            comments_count INTEGER NOT NULL,
            PRIMARY KEY(post_id, captured_at)
        );
        """
    )
    _add_column(connection, "sync_runs", "api_url TEXT")
    _add_column(connection, "sync_runs", "query_fingerprint TEXT")
    _add_column(connection, "sync_runs", "collector_version TEXT")
    _add_column(connection, "sync_windows", "expected_count INTEGER")
    _add_column(connection, "sync_windows", "query_fingerprint TEXT")
    _add_column(connection, "posts", "is_active INTEGER NOT NULL DEFAULT 1")
    connection.execute(
        """
        INSERT OR IGNORE INTO post_metrics_snapshots(
            post_id, captured_at, votes_count, comments_count
        )
        SELECT product_hunt_id, last_seen_at, votes_count, comments_count FROM posts
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO window_posts(window_id, post_id)
        SELECT w.id, p.product_hunt_id
        FROM sync_windows w
        JOIN posts p ON p.featured_at > w.range_start AND p.featured_at < w.range_end
        """
    )
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (SCHEMA_VERSION, utc_now()),
    )
    connection.commit()


def _add_column(connection: sqlite3.Connection, table: str, definition: str) -> None:
    name = definition.split()[0]
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if name not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def begin_run(
    connection: sqlite3.Connection,
    start: str,
    end: str,
    *,
    api_url: str | None = None,
    query_fingerprint: str | None = None,
    collector_version: str = "0.1.0",
) -> int:
    now = utc_now()
    connection.execute(
        """
        UPDATE sync_runs
        SET completed_at = ?, status = 'failed', error = 'superseded by a later sync run'
        WHERE status = 'running'
        """,
        (now,),
    )
    cursor = connection.execute(
        """
        INSERT INTO sync_runs(
            started_at, status, range_start, range_end, api_url,
            query_fingerprint, collector_version
        )
        VALUES (?, 'running', ?, ?, ?, ?, ?)
        """,
        (now, start, end, api_url, query_fingerprint, collector_version),
    )
    connection.commit()
    return int(cursor.lastrowid)


def finish_run(
    connection: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    requests_count: int,
    posts_seen: int,
    rate_limit: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    rate_limit = rate_limit or {}
    connection.execute(
        """
        UPDATE sync_runs
        SET completed_at = ?, status = ?, requests_count = ?, posts_seen = ?,
            rate_limit_limit = ?, rate_limit_remaining = ?, rate_limit_reset = ?, error = ?
        WHERE id = ?
        """,
        (
            utc_now(),
            status,
            requests_count,
            posts_seen,
            rate_limit.get("limit"),
            rate_limit.get("remaining"),
            rate_limit.get("reset"),
            error,
            run_id,
        ),
    )
    connection.commit()


def prepare_window(
    connection: sqlite3.Connection,
    start: str,
    end: str,
    *,
    refresh: bool,
    query_fingerprint: str | None = None,
) -> sqlite3.Row:
    connection.execute(
        """
        INSERT OR IGNORE INTO sync_windows(
            range_start, range_end, updated_at, query_fingerprint
        ) VALUES (?, ?, ?, ?)
        """,
        (start, end, utc_now(), query_fingerprint),
    )
    existing = connection.execute(
        "SELECT * FROM sync_windows WHERE range_start = ? AND range_end = ?", (start, end)
    ).fetchone()
    fingerprint_changed = bool(
        existing
        and existing["query_fingerprint"]
        and existing["query_fingerprint"] != query_fingerprint
    )
    if refresh or fingerprint_changed:
        connection.execute(
            """
            UPDATE sync_windows
            SET cursor = NULL, status = 'pending', pages_fetched = 0, posts_seen = 0,
                expected_count = NULL, query_fingerprint = ?, updated_at = ?, last_error = NULL
            WHERE range_start = ? AND range_end = ?
            """,
            (query_fingerprint, utc_now(), start, end),
        )
        connection.execute("DELETE FROM window_posts WHERE window_id = ?", (int(existing["id"]),))
    elif existing and not existing["query_fingerprint"]:
        connection.execute(
            "UPDATE sync_windows SET query_fingerprint = ? WHERE id = ?",
            (query_fingerprint, int(existing["id"])),
        )
    connection.commit()
    row = connection.execute(
        "SELECT * FROM sync_windows WHERE range_start = ? AND range_end = ?", (start, end)
    ).fetchone()
    assert row is not None
    return row


def save_page(
    connection: sqlite3.Connection,
    *,
    window_id: int,
    posts: Iterable[dict[str, Any]],
    next_cursor: str | None,
    completed: bool,
    expected_count: int | None = None,
) -> int:
    now = utc_now()
    count = 0
    with connection:
        for post in posts:
            count += 1
            connection.execute(
                """
                INSERT INTO posts(
                    product_hunt_id, name, slug, tagline, description, product_hunt_url,
                    website_url, votes_count, comments_count, reviews_count, reviews_rating,
                    featured_at, created_at, raw_json, first_seen_at, last_seen_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(product_hunt_id) DO UPDATE SET
                    name = excluded.name,
                    slug = excluded.slug,
                    tagline = excluded.tagline,
                    description = excluded.description,
                    product_hunt_url = excluded.product_hunt_url,
                    website_url = excluded.website_url,
                    votes_count = excluded.votes_count,
                    comments_count = excluded.comments_count,
                    reviews_count = excluded.reviews_count,
                    reviews_rating = excluded.reviews_rating,
                    featured_at = excluded.featured_at,
                    created_at = excluded.created_at,
                    raw_json = excluded.raw_json,
                    last_seen_at = excluded.last_seen_at,
                    is_active = 1
                """,
                (
                    str(post["id"]),
                    post["name"],
                    post["slug"],
                    post["tagline"],
                    post.get("description"),
                    post["url"],
                    post.get("website"),
                    int(post["votesCount"]),
                    int(post["commentsCount"]),
                    int(post.get("reviewsCount") or 0),
                    float(post.get("reviewsRating") or 0),
                    post.get("featuredAt"),
                    post["createdAt"],
                    json.dumps(post, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
            post_id = str(post["id"])
            connection.execute("DELETE FROM post_topics WHERE post_id = ?", (post_id,))
            connection.execute(
                "INSERT OR IGNORE INTO window_posts(window_id, post_id) VALUES (?, ?)",
                (window_id, post_id),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO post_metrics_snapshots(
                    post_id, captured_at, votes_count, comments_count
                ) VALUES (?, ?, ?, ?)
                """,
                (post_id, now, int(post["votesCount"]), int(post["commentsCount"])),
            )
            for edge in post.get("topics", {}).get("edges", []):
                topic = edge["node"]
                topic_id = str(topic["id"])
                connection.execute(
                    """
                    INSERT INTO topics(product_hunt_id, name, slug) VALUES (?, ?, ?)
                    ON CONFLICT(product_hunt_id) DO UPDATE SET
                        name = excluded.name, slug = excluded.slug
                    """,
                    (topic_id, topic["name"], topic["slug"]),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO post_topics(post_id, topic_id) VALUES (?, ?)",
                    (post_id, topic_id),
                )

        distinct_count = connection.execute(
            "SELECT COUNT(*) FROM window_posts WHERE window_id = ?", (window_id,)
        ).fetchone()[0]
        if completed and expected_count is not None and distinct_count != expected_count:
            raise RuntimeError(
                f"window count mismatch: API reported {expected_count}, collected {distinct_count}"
            )
        if completed:
            connection.execute(
                """
                UPDATE posts SET is_active = 0
                WHERE featured_at > (SELECT range_start FROM sync_windows WHERE id = ?)
                  AND featured_at < (SELECT range_end FROM sync_windows WHERE id = ?)
                  AND product_hunt_id NOT IN (
                    SELECT post_id FROM window_posts WHERE window_id = ?
                  )
                """,
                (window_id, window_id, window_id),
            )
        connection.execute(
            """
            UPDATE sync_windows
            SET cursor = ?, status = ?, pages_fetched = pages_fetched + 1,
                posts_seen = posts_seen + ?, expected_count = ?, updated_at = ?, last_error = NULL
            WHERE id = ?
            """,
            (
                next_cursor,
                "completed" if completed else "running",
                count,
                expected_count,
                now,
                window_id,
            ),
        )
    return count


def fail_window(connection: sqlite3.Connection, window_id: int, error: str) -> None:
    connection.execute(
        """
        UPDATE sync_windows SET status = 'failed', updated_at = ?, last_error = ? WHERE id = ?
        """,
        (utc_now(), error, window_id),
    )
    connection.commit()
