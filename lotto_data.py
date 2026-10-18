"""동행복권 로또 6/45 공개 데이터 수집 및 저장.

공식 홈페이지가 실제로 사용하는 공개 JSON 엔드포인트를 그대로 사용한다.
로그인/쿠키 없이 접근 가능하며, 회차(round) 기준 과거 방향으로 최대 10건씩 응답한다.
  - 최신 회차 확인: GET /selectMainInfo.do
  - 과거 회차 목록: GET /lt645/selectPstLt645InfoNew.do?srchDir=older&srchCursorLtEpsd={cursor}
    -> [cursor-10, cursor-1] 구간의 회차를 반환 (1회 미만은 잘림)
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import requests

BASE_URL = "https://www.dhlottery.co.kr"
HISTORY_URL = f"{BASE_URL}/lt645/selectPstLt645InfoNew.do"

DB_PATH = Path(__file__).parent / "data" / "lotto645.db"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_session = requests.Session()
_session.headers.update(HEADERS)


_RANK_COLUMNS = [
    f"rank{r}_{field}"
    for r in (2, 3, 4, 5)
    for field in ("amount", "winners")
]


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS draws (
            round INTEGER PRIMARY KEY,
            draw_date TEXT NOT NULL,
            n1 INTEGER NOT NULL,
            n2 INTEGER NOT NULL,
            n3 INTEGER NOT NULL,
            n4 INTEGER NOT NULL,
            n5 INTEGER NOT NULL,
            n6 INTEGER NOT NULL,
            bonus INTEGER NOT NULL,
            first_prize_amount INTEGER,
            first_prize_winners INTEGER,
            total_sales INTEGER
        )
        """
    )
    # 기존 DB에는 2~5등 컬럼이 없을 수 있으니 마이그레이션 (회차 상세페이지용으로 추가됨).
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(draws)").fetchall()}
    for col in _RANK_COLUMNS:
        if col not in cols:
            conn.execute(f"ALTER TABLE draws ADD COLUMN {col} INTEGER")
    conn.commit()
    return conn


def _fetch_latest_batch(cursor: int) -> list[dict]:
    """cursor보다 큰 회차를 오름차순 최대 10건 반환 (서버가 실제 최신 회차 이상은 주지 않음).

    주의: cursor=0은 서버가 무효 취급해 빈 목록을 준다 (1회차 이상만 유효).
    """
    resp = _session.get(
        HISTORY_URL,
        params={"srchDir": "latest", "srchCursorLtEpsd": cursor},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", {}).get("list", []) or []


def _fetch_older_batch(cursor: int) -> list[dict]:
    """[cursor-10, cursor-1] 구간의 회차를 반환 (1회 미만은 잘림)."""
    resp = _session.get(
        HISTORY_URL,
        params={"srchDir": "older", "srchCursorLtEpsd": cursor},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", {}).get("list", []) or []


def _parse_record(raw: dict) -> dict:
    ymd = raw["ltRflYmd"]
    record = {
        "round": int(raw["ltEpsd"]),
        "draw_date": f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}",
        "n1": raw["tm1WnNo"],
        "n2": raw["tm2WnNo"],
        "n3": raw["tm3WnNo"],
        "n4": raw["tm4WnNo"],
        "n5": raw["tm5WnNo"],
        "n6": raw["tm6WnNo"],
        "bonus": raw["bnsWnNo"],
        "first_prize_amount": raw.get("rnk1WnAmt"),
        "first_prize_winners": raw.get("rnk1WnNope"),
        "total_sales": raw.get("wholEpsdSumNtslAmt"),
    }
    for r in (2, 3, 4, 5):
        record[f"rank{r}_amount"] = raw.get(f"rnk{r}WnAmt")
        record[f"rank{r}_winners"] = raw.get(f"rnk{r}WnNope")
    return record


_UPSERT_SQL = """
    INSERT OR REPLACE INTO draws
    (round, draw_date, n1, n2, n3, n4, n5, n6, bonus,
     first_prize_amount, first_prize_winners, total_sales,
     rank2_amount, rank2_winners, rank3_amount, rank3_winners,
     rank4_amount, rank4_winners, rank5_amount, rank5_winners)
    VALUES
    (:round, :draw_date, :n1, :n2, :n3, :n4, :n5, :n6, :bonus,
     :first_prize_amount, :first_prize_winners, :total_sales,
     :rank2_amount, :rank2_winners, :rank3_amount, :rank3_winners,
     :rank4_amount, :rank4_winners, :rank5_amount, :rank5_winners)
"""


def sync_draws(progress_callback=None) -> int:
    """DB에 없는 회차를 최신까지 채운다. 새로 저장한 회차 수를 반환한다.

    srchDir=latest는 cursor보다 큰 회차를 오름차순으로 최대 10건 주고,
    실제 최신 회차를 넘어서면 빈 목록을 준다 - 그래서 빈 배치가 곧 종료 조건이다.
    """
    conn = get_db()
    try:
        insert_sql = _UPSERT_SQL

        row = conn.execute("SELECT MAX(round) AS m FROM draws").fetchone()
        cursor = row["m"] or 0
        total_new = 0

        # cursor=0은 서버가 무효 취급하므로, DB가 비어 있으면 1~10회차를
        # older 방향으로 먼저 시드해서 채운다.
        if cursor == 0:
            seed = _fetch_older_batch(11)
            if seed:
                records = [_parse_record(r) for r in seed]
                conn.executemany(insert_sql, records)
                conn.commit()
                total_new += len(records)
                if progress_callback:
                    progress_callback(total_new)
                cursor = max(r["round"] for r in records)

        while True:
            batch = _fetch_latest_batch(cursor)
            if not batch:
                break
            records = [_parse_record(r) for r in batch]
            conn.executemany(insert_sql, records)
            conn.commit()
            total_new += len(records)
            if progress_callback:
                progress_callback(total_new)

            cursor = max(r["round"] for r in records)
            time.sleep(0.15)

        return total_new
    finally:
        conn.close()


def resync_all(progress_callback=None) -> int:
    """1회차부터 최신까지 전체를 다시 받아와 덮어쓴다.

    sync_draws()와 같은 older(시딩) -> latest(순차 진행) 패턴을 쓰되,
    이미 있는 회차도 건너뛰지 않고 전부 다시 UPSERT한다. 스키마에 새 컬럼
    (2~5등 정보 등)을 추가한 뒤, 기존 회차에도 그 값을 채워 넣는 일회성
    백필용이다. 갱신한 회차 수를 반환한다.
    """
    conn = get_db()
    try:
        total = 0
        seed = _fetch_older_batch(11)  # cursor=0은 무효 처리되므로 1~10회차를 먼저 시딩
        cursor = 0
        if seed:
            records = [_parse_record(r) for r in seed]
            conn.executemany(_UPSERT_SQL, records)
            conn.commit()
            total += len(records)
            if progress_callback:
                progress_callback(total)
            cursor = max(r["round"] for r in records)

        while True:
            batch = _fetch_latest_batch(cursor)
            if not batch:
                break
            records = [_parse_record(r) for r in batch]
            conn.executemany(_UPSERT_SQL, records)
            conn.commit()
            total += len(records)
            if progress_callback:
                progress_callback(total)
            cursor = max(r["round"] for r in records)
            time.sleep(0.15)

        return total
    finally:
        conn.close()


def get_all_draws() -> list[sqlite3.Row]:
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM draws ORDER BY round DESC").fetchall()
    finally:
        conn.close()


def get_draw_count() -> int:
    conn = get_db()
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM draws").fetchone()
        return row["c"]
    finally:
        conn.close()


def get_latest_draw() -> sqlite3.Row | None:
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM draws ORDER BY round DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()


PRIZES_PER_PAGE = 20

_SORT_COLUMNS = {
    "round": "round",
    "amount": "first_prize_amount",
    "total_amount": "first_prize_amount * first_prize_winners",
    "sales": "total_sales",
    "winners": "first_prize_winners",
}


def get_draws_page(
    page: int, per_page: int = PRIZES_PER_PAGE, sort: str = "round", order: str = "desc"
) -> list[sqlite3.Row]:
    conn = get_db()
    try:
        offset = (page - 1) * per_page
        column = _SORT_COLUMNS.get(sort, "round")
        direction = "ASC" if order == "asc" else "DESC"
        return conn.execute(
            f"SELECT * FROM draws ORDER BY {column} {direction} LIMIT ? OFFSET ?",
            (per_page, offset),
        ).fetchall()
    finally:
        conn.close()


def get_draw_by_round(round_no: int) -> sqlite3.Row | None:
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM draws WHERE round = ?", (round_no,)).fetchone()
    finally:
        conn.close()


def get_min_max_round() -> tuple[int, int] | None:
    conn = get_db()
    try:
        row = conn.execute("SELECT MIN(round) AS lo, MAX(round) AS hi FROM draws").fetchone()
        if row is None or row["lo"] is None:
            return None
        return row["lo"], row["hi"]
    finally:
        conn.close()
