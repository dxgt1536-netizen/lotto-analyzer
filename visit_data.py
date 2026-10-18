"""일별 방문자수 집계. 쿠키로 하루 1명당 1회만 세어 중복 새로고침을 걸러낸다."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "visits.db"


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_visits (
            visit_date TEXT PRIMARY KEY,
            count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    return conn


def record_visit(visit_date: str) -> None:
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO daily_visits (visit_date, count) VALUES (?, 1)
            ON CONFLICT(visit_date) DO UPDATE SET count = count + 1
            """,
            (visit_date,),
        )
        conn.commit()
    finally:
        conn.close()


def get_today_count(visit_date: str) -> int:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT count FROM daily_visits WHERE visit_date = ?", (visit_date,)
        ).fetchone()
        return row["count"] if row else 0
    finally:
        conn.close()


def get_total_count() -> int:
    conn = get_db()
    try:
        row = conn.execute("SELECT COALESCE(SUM(count), 0) AS total FROM daily_visits").fetchone()
        return row["total"]
    finally:
        conn.close()
