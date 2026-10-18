"""자유게시판 데이터 저장. 로그인 없이 닉네임+비밀번호로 글을 쓰고, 같은 비밀번호로만 지울 수 있다."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path(__file__).parent / "data" / "board.db"

POSTS_PER_PAGE = 20

MAX_NICKNAME = 20
MAX_TITLE = 100
MAX_CONTENT = 5000
MAX_COMMENT = 500

# 명백한 불법/음란 홍보성 스팸을 1차로 걸러내기 위한 금지어. 완벽한 필터는 아니지만
# 흔한 도배성 문구는 대부분 여기 걸린다. 정상적인 글에서 오탐이 잦으면 조정할 것.
BANNED_KEYWORDS = [
    # 불법 도박/토토 홍보
    "토토총판", "카지노총판", "먹튀검증", "안전놀이터 가입", "스포츠토토 가입", "베팅사이트 가입",
    # 마약 등 불법 물품 판매
    "필로폰 판매", "대마 판매", "엑스터시 판매", "떨 팝니다", "아이스 팝니다", "마약 구매",
    # 성매매/조건만남 알선
    "조건만남", "출장안마 예약", "스폰 구함", "스폰서 구함", "성매매 알선",
    # 불법 대출/보이스피싱류 스팸
    "정보이용료 환급", "대출 상담 문의 환영",
]


def contains_banned_keyword(*texts: str) -> bool:
    combined = " ".join(texts)
    return any(kw in combined for kw in BANNED_KEYWORDS)


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            ip_address TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            views INTEGER NOT NULL DEFAULT 0,
            pinned INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    # 기존에 만들어진 DB에는 pinned 컬럼이 없을 수 있으니 마이그레이션.
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(posts)").fetchall()}
    if "pinned" not in cols:
        conn.execute("ALTER TABLE posts ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            nickname TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            content TEXT NOT NULL,
            ip_address TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id)")
    conn.commit()
    return conn


def create_post(
    nickname: str, password: str, title: str, content: str, ip_address: str, pinned: bool = False
) -> int:
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO posts (nickname, password_hash, title, content, ip_address, pinned) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (nickname, generate_password_hash(password), title, content, ip_address, int(pinned)),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_post_count() -> int:
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) AS c FROM posts").fetchone()["c"]
    finally:
        conn.close()


def get_posts_page(page: int) -> list[sqlite3.Row]:
    conn = get_db()
    try:
        offset = (page - 1) * POSTS_PER_PAGE
        return conn.execute(
            "SELECT p.id, p.nickname, p.title, p.created_at, p.views, p.pinned, "
            "COUNT(c.id) AS comment_count "
            "FROM posts p LEFT JOIN comments c ON c.post_id = p.id "
            "GROUP BY p.id "
            "ORDER BY p.pinned DESC, p.id DESC LIMIT ? OFFSET ?",
            (POSTS_PER_PAGE, offset),
        ).fetchall()
    finally:
        conn.close()


def get_post(post_id: int) -> sqlite3.Row | None:
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    finally:
        conn.close()


def increment_views(post_id: int) -> None:
    conn = get_db()
    try:
        conn.execute("UPDATE posts SET views = views + 1 WHERE id = ?", (post_id,))
        conn.commit()
    finally:
        conn.close()


def verify_password(post_id: int, password: str) -> bool:
    post = get_post(post_id)
    if not post:
        return False
    return check_password_hash(post["password_hash"], password)


def delete_post(post_id: int) -> None:
    conn = get_db()
    try:
        conn.execute("DELETE FROM comments WHERE post_id = ?", (post_id,))
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.commit()
    finally:
        conn.close()


def seconds_since_last_post(ip_address: str) -> float | None:
    """이 IP가 마지막으로 글을 쓴 지 몇 초 지났는지. 글이 없으면 None (스팸 도배 방지용)."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT (julianday('now', 'localtime') - julianday(created_at)) * 86400 AS secs "
            "FROM posts WHERE ip_address = ? ORDER BY id DESC LIMIT 1",
            (ip_address,),
        ).fetchone()
        return row["secs"] if row else None
    finally:
        conn.close()


def create_comment(post_id: int, nickname: str, password: str, content: str, ip_address: str) -> int:
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO comments (post_id, nickname, password_hash, content, ip_address) "
            "VALUES (?, ?, ?, ?, ?)",
            (post_id, nickname, generate_password_hash(password), content, ip_address),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_comments(post_id: int) -> list[sqlite3.Row]:
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM comments WHERE post_id = ? ORDER BY id ASC", (post_id,)
        ).fetchall()
    finally:
        conn.close()


def get_comment_count(post_id: int) -> int:
    conn = get_db()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS c FROM comments WHERE post_id = ?", (post_id,)
        ).fetchone()["c"]
    finally:
        conn.close()


def get_comment(comment_id: int) -> sqlite3.Row | None:
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
    finally:
        conn.close()


def verify_comment_password(comment_id: int, password: str) -> bool:
    comment = get_comment(comment_id)
    if not comment:
        return False
    return check_password_hash(comment["password_hash"], password)


def delete_comment(comment_id: int) -> None:
    conn = get_db()
    try:
        conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        conn.commit()
    finally:
        conn.close()


def seconds_since_last_comment(ip_address: str) -> float | None:
    """이 IP가 마지막으로 댓글을 쓴 지 몇 초 지났는지. 댓글이 없으면 None (스팸 도배 방지용)."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT (julianday('now', 'localtime') - julianday(created_at)) * 86400 AS secs "
            "FROM comments WHERE ip_address = ? ORDER BY id DESC LIMIT 1",
            (ip_address,),
        ).fetchone()
        return row["secs"] if row else None
    finally:
        conn.close()
