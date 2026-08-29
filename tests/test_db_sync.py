from __future__ import annotations

from datetime import date

import pytest

from ph_trends.api import Page
from ph_trends.db import begin_run, connect
from ph_trends.sync import month_windows, sync_range


class FakeClient:
    def __init__(self, pages: list[Page | Exception]) -> None:
        self.pages = pages
        self.request_count = 0
        self.rate_limit = {"remaining": 6000}

    def fetch_posts_page(self, **_: str) -> Page:
        self.request_count += 1
        value = self.pages.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_month_windows_respect_partial_boundaries() -> None:
    assert month_windows(date(2026, 1, 15), date(2026, 3, 3)) == [
        (date(2026, 1, 15), date(2026, 2, 1)),
        (date(2026, 2, 1), date(2026, 3, 1)),
        (date(2026, 3, 1), date(2026, 3, 3)),
    ]


def test_upsert_is_idempotent(tmp_path, make_post) -> None:
    connection = connect(tmp_path / "test.sqlite3")
    first = FakeClient([Page([make_post("1", votes=10)], False, None)])
    sync_range(connection, first, start=date(2026, 6, 1), end=date(2026, 7, 1))
    second = FakeClient([Page([make_post("1", votes=20)], False, None)])
    sync_range(
        connection,
        second,
        start=date(2026, 6, 1),
        end=date(2026, 7, 1),
        refresh=True,
    )
    row = connection.execute("SELECT * FROM posts").fetchone()
    assert connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 1
    assert row["votes_count"] == 20
    assert connection.execute("SELECT COUNT(*) FROM post_topics").fetchone()[0] == 1


def test_resume_uses_saved_cursor(tmp_path, make_post) -> None:
    connection = connect(tmp_path / "test.sqlite3")
    failing = FakeClient(
        [Page([make_post("1")], True, "cursor-1"), RuntimeError("temporary failure")]
    )
    with pytest.raises(RuntimeError, match="temporary failure"):
        sync_range(connection, failing, start=date(2026, 6, 1), end=date(2026, 7, 1))
    window = connection.execute("SELECT * FROM sync_windows").fetchone()
    assert window["cursor"] == "cursor-1"
    assert window["status"] == "failed"

    class ResumingClient(FakeClient):
        def fetch_posts_page(self, **kwargs: str) -> Page:
            assert kwargs["after"] == "cursor-1"
            return super().fetch_posts_page(**kwargs)

    resumed = ResumingClient([Page([make_post("2")], False, None)])
    sync_range(connection, resumed, start=date(2026, 6, 1), end=date(2026, 7, 1))
    assert connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 2


def test_new_run_marks_abandoned_run_failed(tmp_path) -> None:
    connection = connect(tmp_path / "test.sqlite3")
    old_id = begin_run(connection, "2026-01-01", "2026-02-01")
    begin_run(connection, "2026-02-01", "2026-03-01")
    old = connection.execute("SELECT * FROM sync_runs WHERE id = ?", (old_id,)).fetchone()
    assert old["status"] == "failed"
    assert old["error"] == "superseded by a later sync run"


def test_total_count_mismatch_rolls_back_page(tmp_path, make_post) -> None:
    connection = connect(tmp_path / "test.sqlite3")
    client = FakeClient([Page([make_post("1")], False, None, total_count=2)])
    with pytest.raises(RuntimeError, match="window count mismatch"):
        sync_range(connection, client, start=date(2026, 6, 1), end=date(2026, 7, 1))
    assert connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 0


def test_invalid_cursor_is_rejected_before_page_commit(tmp_path, make_post) -> None:
    connection = connect(tmp_path / "test.sqlite3")
    client = FakeClient([Page([make_post("1")], True, None, total_count=2)])
    with pytest.raises(RuntimeError, match="cursor did not advance"):
        sync_range(connection, client, start=date(2026, 6, 1), end=date(2026, 7, 1))
    assert connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 0
