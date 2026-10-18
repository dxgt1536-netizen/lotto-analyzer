from __future__ import annotations

import datetime
import hmac
import time
from collections import defaultdict
from urllib.parse import urlparse

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

import board_data
import config
import lotto_data
import lotto_stats
import other_lottery
import visit_data

app = Flask(__name__)
# Caddy 리버스 프록시 뒤에서 돌아가므로, X-Forwarded-For를 신뢰해야 request.remote_addr가
# 실제 방문자 IP가 된다 (게시판 스팸 방지에 씀).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
# 요청 본문 크기를 명시적으로 제한 (게시글 최대 5000자보다 넉넉하게).
# 제한이 없으면 거대한 POST 요청 하나로 서버 메모리/CPU를 잡아먹는 공격이 가능해진다.
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024  # 256KB


SQLITE_MAX_INT = 9_223_372_036_854_775_807


def _reject_oversized_int(value: int) -> None:
    """SQLite INTEGER(64비트)보다 큰 값을 그대로 바인딩하면 OverflowError로 500이 난다.
    <int:...> URL 파라미터는 Python 임의 정밀도라 그런 값도 그대로 들어올 수 있으므로,
    조회 전에 걸러서 404로 처리한다 (어차피 존재할 수 없는 id/round이기도 하다)."""
    if value > SQLITE_MAX_INT:
        abort(404)


def _safe_int(value, default, minimum=None, maximum=None):
    """쿼리 파라미터를 정수로 바꾸되, 이상한 값이 와도 500 에러 대신 기본값으로 넘어가게 한다."""
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(result, minimum)
    if maximum is not None:
        result = min(result, maximum)
    return result


def _is_same_site_request() -> bool:
    """Origin 헤더가 있는데 우리 사이트가 아니면 다른 사이트에서 자동으로 쏜 요청(CSRF)으로 본다.
    Origin이 아예 없는 경우(일부 구형 브라우저, 직접 폼 제출 등)는 막지 않는다 - 완벽한 CSRF
    방어는 아니지만, 악성 사이트의 자동 폼 제출을 통한 스팸/삭제 시도는 대부분 막아준다."""
    origin = request.headers.get("Origin")
    if not origin:
        return True
    allowed_host = urlparse(config.SITE_URL).netloc if config.SITE_URL else request.host
    return urlparse(origin).netloc == allowed_host


_recent_attempts: dict[str, list[float]] = defaultdict(list)


def _rate_limited(key: str, max_attempts: int, window_seconds: float) -> bool:
    """key(보통 'action:ip')당 최근 window_seconds 안에 시도 횟수가 max_attempts를 넘었는지.
    메모리에만 저장하므로 서버 재시작하면 초기화되지만, 무차별 대입 완화 목적으로는 충분하다."""
    now = time.time()
    attempts = _recent_attempts[key]
    while attempts and attempts[0] < now - window_seconds:
        attempts.pop(0)
    if len(attempts) >= max_attempts:
        return True
    attempts.append(now)
    return False


@app.template_filter("comma")
def comma_filter(value):
    if value is None:
        return "-"
    return f"{value:,}"


_TRACKED_PAGE_ENDPOINTS = {
    "index", "stats", "recommend", "fortune", "simulator",
    "tax_calculator", "prizes", "board_list", "board_write", "board_view",
}


@app.before_request
def _track_visit():
    """쿠키에 오늘 날짜가 없는 방문자만 하루 1회로 세어 순 방문자수를 집계한다."""
    if request.method != "GET" or request.endpoint not in _TRACKED_PAGE_ENDPOINTS:
        return
    today = datetime.date.today().isoformat()
    if request.cookies.get("visited_date") != today:
        visit_data.record_visit(today)
        request.environ["_new_visit_date"] = today


@app.after_request
def _set_visit_cookie(response):
    today = request.environ.get("_new_visit_date")
    if today:
        response.set_cookie("visited_date", today, max_age=60 * 60 * 24 * 2, samesite="Lax")
    return response


@app.context_processor
def inject_seo_config():
    today = datetime.date.today().isoformat()
    return {
        "site_name": config.SITE_NAME,
        "site_url": config.SITE_URL,
        "site_description": config.SITE_DESCRIPTION,
        "adsense_client_id": config.ADSENSE_CLIENT_ID,
        "adsense_slot_top": config.ADSENSE_SLOT_TOP,
        "adsense_slot_inline": config.ADSENSE_SLOT_INLINE,
        "ads_enabled": config.ADS_ENABLED,
        "google_site_verification": config.GOOGLE_SITE_VERIFICATION,
        "naver_site_verification": config.NAVER_SITE_VERIFICATION,
        "today_visits": visit_data.get_today_count(today),
        "total_visits": visit_data.get_total_count(),
    }


@app.route("/<fname>.html")
def site_verification_file(fname):
    """구글/네이버 등 'HTML 파일 업로드' 방식 소유확인용.
    이런 파일들은 내용이 항상 'xxx-site-verification: 파일명.html' 한 줄로 고정돼 있어
    파일을 실제로 둘 필요 없이 이름만 알면 즉석에서 만들어 줄 수 있다.
    """
    if fname.startswith("google") and fname.replace("google", "", 1).isalnum():
        return Response(f"google-site-verification: {fname}.html", mimetype="text/html")
    if fname.startswith("naver") and fname.replace("naver", "", 1).isalnum():
        return Response(f"naver-site-verification: {fname}.html", mimetype="text/html")
    abort(404)


@app.route("/favicon.ico")
def favicon_ico():
    # 브라우저/크롤러가 <link> 태그 없이도 관습적으로 찾는 루트 경로.
    return redirect(url_for("static", filename="favicon.ico"))


@app.route("/robots.txt")
def robots_txt():
    lines = ["User-agent: *", "Allow: /"]
    if config.SITE_URL:
        lines.append(f"Sitemap: {config.SITE_URL}/sitemap.xml")
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


SITEMAP_RECENT_ROUNDS = 200


@app.route("/sitemap.xml")
def sitemap_xml():
    base = config.SITE_URL or request.url_root.rstrip("/")
    pages = [
        "/", "/stats", "/recommend", "/fortune", "/simulator",
        "/tax-calculator", "/prizes", "/other-games", "/board",
    ]
    urls = "".join(f"<url><loc>{base}{p}</loc></url>" for p in pages)

    bounds = lotto_data.get_min_max_round()
    if bounds:
        min_round, max_round = bounds
        # 회차 페이지를 전부 넣으면(1000개+) 비슷한 페이지가 너무 많아 크롤링 예산이
        # 분산되므로, 최근 것만 남기고 나머지는 역대 당첨금 목록의 내부 링크로만 연결한다.
        recent_start = max(min_round, max_round - SITEMAP_RECENT_ROUNDS + 1)
        urls += "".join(
            f"<url><loc>{base}/prizes/{r}</loc></url>" for r in range(recent_start, max_round + 1)
        )

    xml = f'<?xml version="1.0" encoding="UTF-8"?>' \
          f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(xml, mimetype="application/xml")


@app.route("/ads.txt")
def ads_txt():
    if not config.ADSENSE_CLIENT_ID:
        return Response("", mimetype="text/plain")
    pub_id = config.ADSENSE_CLIENT_ID.replace("ca-pub-", "pub-")
    return Response(
        f"google.com, {pub_id}, DIRECT, f08c47fec0942fa0\n", mimetype="text/plain"
    )


@app.route("/")
def index():
    latest = lotto_data.get_latest_draw()
    count = lotto_data.get_draw_count()
    recent = lotto_stats.recent_draws(limit=5)
    return render_template(
        "index.html", latest=latest, count=count, recent=recent
    )


RECENT_N = 50


@app.route("/stats")
def stats():
    freq = lotto_stats.number_frequency()
    recent_freq = lotto_stats.recent_number_frequency(RECENT_N)
    hot, cold = lotto_stats.hot_cold_numbers(top_n=6)
    recent_hot, recent_cold = lotto_stats.hot_cold_numbers(top_n=6, freq=recent_freq)
    odd_even = lotto_stats.odd_even_ratio()
    low_high = lotto_stats.low_high_ratio()
    sum_curve = lotto_stats.sum_distribution_curve()
    pairs = lotto_stats.top_pairs(top_n=10)
    max_freq = max(freq.values()) if freq else 0
    max_recent_freq = max(recent_freq.values()) if recent_freq else 0
    return render_template(
        "stats.html",
        freq=freq,
        max_freq=max_freq,
        recent_freq=recent_freq,
        max_recent_freq=max_recent_freq,
        recent_n=min(RECENT_N, lotto_data.get_draw_count()),
        hot=hot,
        cold=cold,
        recent_hot=recent_hot,
        recent_cold=recent_cold,
        odd_even=odd_even,
        low_high=low_high,
        sum_curve=sum_curve,
        pairs=pairs,
        count=lotto_data.get_draw_count(),
    )


_PICKERS = {
    "random": lotto_stats.random_pick,
    "hot": lotto_stats.hot_pick,
    "cold": lotto_stats.cold_pick,
}


@app.route("/recommend")
def recommend():
    mode = request.args.get("mode", "random")
    count = _safe_int(request.args.get("count"), 5, 1, 10)
    # 반자동은 빈 구슬 채우기를 클라이언트에서 처리하므로 초기 picks가 필요 없다.
    picks = [] if mode == "semi" else _PICKERS.get(mode, lotto_stats.random_pick)(count=count)
    return render_template("recommend.html", picks=picks, mode=mode, count=count)


@app.route("/api/recommend")
def api_recommend():
    mode = request.args.get("mode", "random")
    count = _safe_int(request.args.get("count"), 5, 1, 10)
    picks = _PICKERS.get(mode, lotto_stats.random_pick)(count=count)
    return jsonify({"mode": mode, "picks": picks})


@app.route("/simulator")
def simulator():
    return render_template("simulator.html")


@app.route("/tax-calculator")
def tax_calculator():
    return render_template("tax_calculator.html")


def _pagination_window(page: int, total_pages: int, spread: int = 2) -> list[int | None]:
    """페이지네이션에 보여줄 번호만 추리고, 건너뛴 구간은 None(생략 표시)으로 채운다."""
    if total_pages <= 1:
        return [1]
    keep = {1, total_pages}
    for p in range(page - spread, page + spread + 1):
        if 1 <= p <= total_pages:
            keep.add(p)
    ordered = sorted(keep)
    result: list[int | None] = []
    prev = None
    for p in ordered:
        if prev is not None and p - prev > 1:
            result.append(None)
        result.append(p)
        prev = p
    return result


@app.route("/fortune")
def fortune():
    return render_template("fortune.html")


@app.route("/other-games")
def other_games():
    games = other_lottery.get_all_games_status()
    return render_template("other_games.html", games=games)


@app.route("/prizes")
def prizes():
    page = _safe_int(request.args.get("page"), 1, minimum=1)
    sort = request.args.get("sort", "round")
    if sort not in ("round", "amount", "total_amount", "sales", "winners"):
        sort = "round"
    order = request.args.get("order", "desc")
    if order not in ("asc", "desc"):
        order = "desc"

    total = lotto_data.get_draw_count()
    total_pages = max((total + lotto_data.PRIZES_PER_PAGE - 1) // lotto_data.PRIZES_PER_PAGE, 1)
    page = min(page, total_pages)
    draws = lotto_data.get_draws_page(page, sort=sort, order=order)
    return render_template(
        "prizes.html",
        draws=draws,
        page=page,
        total_pages=total_pages,
        total=total,
        sort=sort,
        order=order,
        pages_window=_pagination_window(page, total_pages),
    )


@app.route("/prizes/<int:round_no>")
def prize_detail(round_no):
    _reject_oversized_int(round_no)
    draw = lotto_data.get_draw_by_round(round_no)
    if not draw:
        abort(404)
    bounds = lotto_data.get_min_max_round()
    min_round, max_round = bounds if bounds else (round_no, round_no)
    return render_template(
        "prize_detail.html",
        draw=draw,
        has_prev=round_no > min_round,
        has_next=round_no < max_round,
    )


BOARD_POST_COOLDOWN_SECONDS = 15


@app.route("/board")
def board_list():
    page = _safe_int(request.args.get("page"), 1, minimum=1)
    total = board_data.get_post_count()
    total_pages = max((total + board_data.POSTS_PER_PAGE - 1) // board_data.POSTS_PER_PAGE, 1)
    page = min(page, total_pages)
    posts = board_data.get_posts_page(page)
    return render_template(
        "board_list.html", posts=posts, page=page, total_pages=total_pages, total=total
    )


@app.route("/board/write", methods=["GET", "POST"])
def board_write():
    if request.method == "GET":
        return render_template("board_write.html", error=None, form={})

    ip = request.remote_addr or "unknown"

    if not _is_same_site_request():
        abort(403)

    # 검증 실패로 끝나는 요청은 실제 글이 안 쌓여 아래 쿨다운 체크를 피해가므로,
    # 성공/실패와 무관하게 "시도 자체"를 IP당 짧은 시간에 제한한다.
    if _rate_limited(f"write:{ip}", max_attempts=5, window_seconds=20):
        return render_template(
            "board_write.html", error="요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.", form={}
        )

    form = {
        "nickname": request.form.get("nickname", "").strip(),
        "title": request.form.get("title", "").strip(),
        "content": request.form.get("content", "").strip(),
    }
    password = request.form.get("password", "")

    # 봇 방지용 허니팟: 사람 눈에는 안 보이지만 봇은 채우는 경우가 많은 필드.
    if request.form.get("homepage"):
        return redirect(url_for("board_list"))

    error = None
    if not form["nickname"] or len(form["nickname"]) > board_data.MAX_NICKNAME:
        error = f"닉네임을 1~{board_data.MAX_NICKNAME}자로 입력해주세요."
    elif not password or len(password) < 4:
        error = "비밀번호를 4자 이상 입력해주세요 (글 삭제할 때 필요해요)."
    elif not form["title"] or len(form["title"]) > board_data.MAX_TITLE:
        error = f"제목을 1~{board_data.MAX_TITLE}자로 입력해주세요."
    elif not form["content"] or len(form["content"]) > board_data.MAX_CONTENT:
        error = f"내용을 1~{board_data.MAX_CONTENT}자로 입력해주세요."
    elif board_data.contains_banned_keyword(form["title"], form["content"]):
        error = "제목이나 내용에 등록할 수 없는 표현이 포함되어 있습니다."

    if not error:
        secs = board_data.seconds_since_last_post(ip)
        if secs is not None and secs < BOARD_POST_COOLDOWN_SECONDS:
            error = f"글을 너무 빨리 연달아 쓰고 있어요. {int(BOARD_POST_COOLDOWN_SECONDS - secs) + 1}초 후 다시 시도해주세요."

    if error:
        return render_template("board_write.html", error=error, form=form)

    post_id = board_data.create_post(form["nickname"], password, form["title"], form["content"], ip)
    return redirect(url_for("board_view", post_id=post_id))


@app.route("/board/<int:post_id>")
def board_view(post_id):
    _reject_oversized_int(post_id)
    post = board_data.get_post(post_id)
    if not post:
        abort(404)
    board_data.increment_views(post_id)
    comments = board_data.get_comments(post_id)
    return render_template("board_view.html", post=post, comments=comments, error=None, comment_error=None)


@app.route("/board/<int:post_id>/delete", methods=["POST"])
def board_delete(post_id):
    _reject_oversized_int(post_id)
    post = board_data.get_post(post_id)
    if not post:
        abort(404)

    if not _is_same_site_request():
        abort(403)

    ip = request.remote_addr or "unknown"
    comments = board_data.get_comments(post_id)
    # 비밀번호 무차별 대입(특히 관리자 마스터 비밀번호) 시도를 늦추기 위한 제한.
    if _rate_limited(f"delete:{ip}", max_attempts=8, window_seconds=30):
        return render_template(
            "board_view.html", post=post, comments=comments, error="시도가 너무 잦습니다. 잠시 후 다시 시도해주세요.", comment_error=None
        )

    password = request.form.get("password", "")
    is_admin = bool(config.BOARD_ADMIN_PASSWORD) and hmac.compare_digest(
        password, config.BOARD_ADMIN_PASSWORD
    )
    if not is_admin and not board_data.verify_password(post_id, password):
        return render_template(
            "board_view.html", post=post, comments=comments, error="비밀번호가 일치하지 않습니다.", comment_error=None
        )
    board_data.delete_post(post_id)
    return redirect(url_for("board_list"))


BOARD_COMMENT_COOLDOWN_SECONDS = 5


@app.route("/board/<int:post_id>/comment", methods=["POST"])
def board_comment_write(post_id):
    _reject_oversized_int(post_id)
    post = board_data.get_post(post_id)
    if not post:
        abort(404)

    if not _is_same_site_request():
        abort(403)

    ip = request.remote_addr or "unknown"
    comments = board_data.get_comments(post_id)

    if _rate_limited(f"comment:{ip}", max_attempts=8, window_seconds=20):
        return render_template(
            "board_view.html", post=post, comments=comments, error=None,
            comment_error="요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.",
        )

    nickname = request.form.get("nickname", "").strip()
    content = request.form.get("content", "").strip()
    password = request.form.get("password", "")

    # 봇 방지용 허니팟.
    if request.form.get("homepage"):
        return redirect(url_for("board_view", post_id=post_id))

    error = None
    if not nickname or len(nickname) > board_data.MAX_NICKNAME:
        error = f"닉네임을 1~{board_data.MAX_NICKNAME}자로 입력해주세요."
    elif not password or len(password) < 4:
        error = "비밀번호를 4자 이상 입력해주세요 (댓글 삭제할 때 필요해요)."
    elif not content or len(content) > board_data.MAX_COMMENT:
        error = f"댓글을 1~{board_data.MAX_COMMENT}자로 입력해주세요."
    elif board_data.contains_banned_keyword(content):
        error = "댓글에 등록할 수 없는 표현이 포함되어 있습니다."

    if not error:
        secs = board_data.seconds_since_last_comment(ip)
        if secs is not None and secs < BOARD_COMMENT_COOLDOWN_SECONDS:
            error = f"댓글을 너무 빨리 연달아 쓰고 있어요. {int(BOARD_COMMENT_COOLDOWN_SECONDS - secs) + 1}초 후 다시 시도해주세요."

    if error:
        return render_template(
            "board_view.html", post=post, comments=comments, error=None, comment_error=error
        )

    board_data.create_comment(post_id, nickname, password, content, ip)
    return redirect(url_for("board_view", post_id=post_id) + "#comments")


@app.route("/board/<int:post_id>/comment/<int:comment_id>/delete", methods=["POST"])
def board_comment_delete(post_id, comment_id):
    _reject_oversized_int(post_id)
    _reject_oversized_int(comment_id)
    post = board_data.get_post(post_id)
    if not post:
        abort(404)
    comment = board_data.get_comment(comment_id)
    if not comment or comment["post_id"] != post_id:
        abort(404)

    if not _is_same_site_request():
        abort(403)

    ip = request.remote_addr or "unknown"
    comments = board_data.get_comments(post_id)
    if _rate_limited(f"comment_delete:{ip}", max_attempts=8, window_seconds=30):
        return render_template(
            "board_view.html", post=post, comments=comments, error=None,
            comment_error="시도가 너무 잦습니다. 잠시 후 다시 시도해주세요.",
        )

    password = request.form.get("password", "")
    is_admin = bool(config.BOARD_ADMIN_PASSWORD) and hmac.compare_digest(
        password, config.BOARD_ADMIN_PASSWORD
    )
    if not is_admin and not board_data.verify_comment_password(comment_id, password):
        return render_template(
            "board_view.html", post=post, comments=comments, error=None,
            comment_error="비밀번호가 일치하지 않습니다.",
        )
    board_data.delete_comment(comment_id)
    return redirect(url_for("board_view", post_id=post_id) + "#comments")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
