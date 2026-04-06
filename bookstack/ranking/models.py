"""SQLite models for contribution ranking data."""

import os
import sqlite3
from datetime import datetime
from typing import Any

DB_PATH = os.environ.get("RANKING_DB_PATH", "/app/data/ranking.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                taken_at TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                total_pages INTEGER DEFAULT 0,
                total_chars INTEGER DEFAULT 0,
                created_pages INTEGER DEFAULT 0,
                updated_pages INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_taken
                ON snapshots(taken_at);
            CREATE INDEX IF NOT EXISTS idx_snapshots_user
                ON snapshots(user_id);

            CREATE TABLE IF NOT EXISTS page_ownership (
                page_id INTEGER PRIMARY KEY,
                creator_id INTEGER NOT NULL,
                char_count INTEGER DEFAULT 0,
                last_updated TEXT
            );

            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,
                user_email TEXT NOT NULL,
                target_page_id INTEGER,
                target_page_name TEXT DEFAULT '',
                target_book_name TEXT DEFAULT '',
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                char_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                admin_comment TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                reviewed_at TEXT DEFAULT '',
                reviewed_by TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_submissions_status
                ON submissions(status);
            CREATE INDEX IF NOT EXISTS idx_submissions_user
                ON submissions(user_email);
        """)


def save_snapshot(
    taken_at: str,
    user_id: int,
    user_name: str,
    total_pages: int,
    total_chars: int,
    created_pages: int,
    updated_pages: int,
) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO snapshots
               (taken_at, user_id, user_name, total_pages, total_chars, created_pages, updated_pages)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (taken_at, user_id, user_name, total_pages, total_chars, created_pages, updated_pages),
        )


def save_page_ownership(page_id: int, creator_id: int, char_count: int) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO page_ownership (page_id, creator_id, char_count, last_updated)
               VALUES (?, ?, ?, ?)""",
            (page_id, creator_id, char_count, datetime.now().isoformat()),
        )


def get_ranking(period: str = "all") -> list[dict[str, Any]]:
    """Get ranking data for a given period.

    period: 'week', 'month', 'year', 'all'
    Returns list of {user_id, user_name, total_chars, total_pages, rank}
    """
    now = datetime.now()
    if period == "week":
        # Current week (Monday start)
        from datetime import timedelta
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0)
        date_filter = start.strftime("%Y-%m-%d")
    elif period == "month":
        date_filter = now.strftime("%Y-%m-01")
    elif period == "year":
        date_filter = now.strftime("%Y-01-01")
    else:
        date_filter = "2000-01-01"

    with get_db() as conn:
        # Get latest snapshot per user after date_filter
        rows = conn.execute(
            """
            WITH latest AS (
                SELECT user_id, user_name, total_chars, total_pages,
                       ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY taken_at DESC) as rn
                FROM snapshots
                WHERE taken_at >= ?
            ),
            baseline AS (
                SELECT user_id, total_chars, total_pages,
                       ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY taken_at ASC) as rn
                FROM snapshots
                WHERE taken_at >= ?
            )
            SELECT
                l.user_id,
                l.user_name,
                (l.total_chars - COALESCE(b.total_chars, 0)) as period_chars,
                (l.total_pages - COALESCE(b.total_pages, 0)) as period_pages,
                l.total_chars,
                l.total_pages
            FROM latest l
            LEFT JOIN baseline b ON l.user_id = b.user_id AND b.rn = 1
            WHERE l.rn = 1
            ORDER BY period_chars DESC
            """,
            (date_filter, date_filter),
        ).fetchall()

        result = []
        for i, row in enumerate(rows, 1):
            result.append({
                "rank": i,
                "user_id": row["user_id"],
                "user_name": row["user_name"],
                "period_chars": row["period_chars"],
                "period_pages": row["period_pages"],
                "total_chars": row["total_chars"],
                "total_pages": row["total_pages"],
            })
        return result


def create_submission(
    user_name: str, user_email: str,
    target_page_id: int | None, target_page_name: str, target_book_name: str,
    title: str, content: str,
) -> int:
    import re
    text = re.sub(r"<[^>]+>", "", content)
    text = re.sub(r"\s+", " ", text).strip()
    char_count = len(text)
    now = datetime.now().isoformat()
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO submissions
               (user_name, user_email, target_page_id, target_page_name, target_book_name,
                title, content, char_count, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (user_name, user_email, target_page_id, target_page_name, target_book_name,
             title, content, char_count, now),
        )
        return cur.lastrowid


def get_submissions(status: str | None = None) -> list[dict[str, Any]]:
    with get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM submissions WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM submissions ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
        return [dict(row) for row in rows]


def get_submission(sub_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM submissions WHERE id = ?", (sub_id,)).fetchone()
        return dict(row) if row else None


def update_submission_status(sub_id: int, status: str, admin_comment: str = "", reviewed_by: str = "") -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE submissions SET status=?, admin_comment=?, reviewed_at=?, reviewed_by=? WHERE id=?",
            (status, admin_comment, datetime.now().isoformat(), reviewed_by, sub_id),
        )


def get_user_submissions_stats() -> list[dict[str, Any]]:
    """Get approved submission stats per user for ranking."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT user_name, user_email,
                      COUNT(*) as total_submissions,
                      SUM(char_count) as total_chars,
                      SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) as approved_count,
                      SUM(CASE WHEN status='approved' THEN char_count ELSE 0 END) as approved_chars
               FROM submissions
               GROUP BY user_email
               ORDER BY approved_chars DESC"""
        ).fetchall()
        return [dict(row) for row in rows]


def get_user_detail(user_id: int) -> list[dict[str, Any]]:
    """Get all snapshots for a specific user."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM snapshots WHERE user_id = ? ORDER BY taken_at DESC LIMIT 100",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
