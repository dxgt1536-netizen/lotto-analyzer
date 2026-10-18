"""동행복권에서 판매하는 기타 복권(즉석복권/전자복권)의 1등 당첨 현황 조회.

로또처럼 회차 단위가 아니라, 동행복권이 제공하는 '1등 당첨현황' 공개 API
(selectFstWnList.do)를 그대로 쓴다. 이 API는 게임별 전체 1등 당첨 이력
(당첨일·당첨금·건수)과 확률/평균/최고/최저 통계를 로그인 없이 제공한다.
"""

from __future__ import annotations

import re
import time
from datetime import date, timedelta

import requests

BASE_URL = "https://www.dhlottery.co.kr"
FIRST_WIN_URL = f"{BASE_URL}/inslt/isnt/selectFstWnList.do"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json;charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "AJAX": "true",
    "Origin": BASE_URL,
}

_session = requests.Session()
_session.headers.update(HEADERS)

# 게임코드 -> (이름, 분류, 실시간 잭팟 API 경로 prefix, 게임 소개 페이지 경로)
GAMES = {
    "LI21": ("트리플럭", "즉석복권", "/inslt/isnt", "/inslt/isnt/tlGmInfo"),
    "LI23": ("캐치미", "즉석복권", "/inslt/isnt", "/inslt/isnt/cmGmInfo"),
    "LI22": ("트레져헌터", "즉석복권", "/inslt/isnt", "/inslt/isnt/thGmInfo"),
    "LD20": ("더블잭마이더스", "즉석복권", "/inslt/isnt", "/inslt/isnt/djGmInfo"),
    "LD10": ("스피드키노", "추첨식 복권", "/srfllt", "/srfllt/skGmInfo"),
    "LD14": ("파워볼", "추첨식 복권", "/srfllt", "/srfllt/pbGmInfo"),
    "LD11": ("메가빙고", "추첨식 복권", "/srfllt", "/srfllt/mbGmInfo"),
}

DISPLAY_COUNT = 5  # 카드에 보여주는 최근 당첨 이력 건수
HISTORY_COUNT = 20  # 예상 당첨일 계산(평균 간격)에 쓰는 표본 건수

_API_CACHE_TTL = 300  # 5분 - 실시간 잭팟/당첨이력용
_PROB_CACHE_TTL = 6 * 60 * 60  # 6시간 - 게임 확률은 규칙이 안 바뀌는 한 고정값이라 길게
_cache: dict[str, tuple[float, dict]] = {}
_prob_cache: dict[str, tuple[float, str | None]] = {}


def _cached_get(url: str, params: dict, cache_key: str) -> dict:
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and now - cached[0] < _API_CACHE_TTL:
        return cached[1]
    resp = _session.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("data", {}) or {}
    _cache[cache_key] = (now, data)
    return data


_RANK1_PROB_RE = re.compile(r'1\s*등</div>\s*<div class="txt-tail">\s*([^<]+)')


def _fetch_rank1_probability(code: str, info_path: str) -> str | None:
    """게임 소개 페이지 상단 요약박스에 있는 공식 1등 당첨확률(예: '1/613,480.2')을 가져온다.

    API에는 이 값이 없어 소개 페이지 HTML을 직접 파싱해야 한다. 정적인 값이라
    캐시를 길게 둔다. 페이지 구조가 바뀌어 못 찾으면 조용히 None을 반환한다
    (틀린 값을 보여주느니 표시를 안 하는 쪽이 낫다).
    """
    now = time.time()
    cached = _prob_cache.get(code)
    if cached and now - cached[0] < _PROB_CACHE_TTL:
        return cached[1]
    try:
        resp = _session.get(f"{BASE_URL}{info_path}", params={"stGmTypeCd": code}, timeout=10)
        resp.raise_for_status()
        match = _RANK1_PROB_RE.search(resp.text)
        prob = match.group(1).strip() if match else None
    except requests.RequestException:
        prob = None
    _prob_cache[code] = (now, prob)
    return prob


def _fetch_first_rank(code: str) -> dict:
    """1등 당첨현황: 최근 이력 몇 건 + 평균/최고/최저 당첨금. 실패 시 빈 값.

    API가 함께 주는 ltWnPrb 필드는 이름과 달리 게임 공식 소개 페이지의
    이론적 당첨확률(예: 스피드키노 1/613,480.2)과 값이 전혀 다르고, 오히려
    평균 당첨금(ltWnAvg)과 값이 거의 같아 실제 의미가 불확실하므로 쓰지 않는다.
    """
    try:
        data = _cached_get(
            FIRST_WIN_URL,
            {"stGmTypeCd": code, "pageNum": 1, "recordCountPerPage": HISTORY_COUNT},
            f"fstwn:{code}",
        )
    except (requests.RequestException, ValueError):
        return {"total": 0, "list": [], "info": {}}
    return {
        "total": data.get("total", 0),
        "list": data.get("list", []) or [],
        "info": data.get("info") or {},
    }


def _predict_status(predicted_date: str | None) -> str:
    """예상일로부터 얼마나 지났는지에 따라 강조 단계를 매긴다: 1일 이상 지나면
    'warning', 7일 이상 지나면 'danger', 그 전이거나 계산 불가면 'normal'."""
    if not predicted_date:
        return "normal"
    try:
        days_overdue = (date.today() - date.fromisoformat(predicted_date)).days
    except ValueError:
        return "normal"
    if days_overdue >= 7:
        return "danger"
    if days_overdue >= 1:
        return "warning"
    return "normal"


def _estimate_next_win_date(history: list[dict]) -> str | None:
    """최근 당첨일자들의 평균 간격으로 다음 1등 예상일을 추정한다.

    통계적 근거가 있는 예측이 아니라 재미용 추정치다 - 복권 추첨은 매 회
    독립적인 무작위 확률이라 과거 당첨 간격이 다음 당첨 시점을 보장하지 않는다.
    """
    dates = sorted({row["ltWnDt"] for row in history if row.get("ltWnDt")})
    if len(dates) < 2:
        return None
    try:
        parsed = [date.fromisoformat(d) for d in dates]
    except ValueError:
        return None
    intervals = [(parsed[i + 1] - parsed[i]).days for i in range(len(parsed) - 1)]
    avg_interval = sum(intervals) / len(intervals)
    return (parsed[-1] + timedelta(days=round(avg_interval))).isoformat()


def _history_amount_stats(history: list[dict]) -> tuple[int | None, int | None, int | None]:
    """API가 info(평균/최고/최저)를 안 주는 게임(트리플럭·캐치미 등)을 위한 대체 계산.

    최근 이력(history)의 당첨금만으로 평균/최고/최저를 직접 구한다. API가 주는
    전체 기간 통계보다는 표본이 적지만, info 자체가 없는 것보다는 낫다.
    """
    amounts = [row["ltWnAmt"] for row in history if row.get("ltWnAmt")]
    if not amounts:
        return None, None, None
    return round(sum(amounts) / len(amounts)), max(amounts), min(amounts)


def _fetch_jackpots(prefix: str) -> dict[str, dict]:
    """같은 분류(즉석/전자) 게임 전체의 실시간 잭팟을 한 번에 반환. 실패 시 빈 dict."""
    try:
        data = _cached_get(f"{BASE_URL}{prefix}/selectRtmlramWnlist.do", {}, f"jackpot:{prefix}")
    except (requests.RequestException, ValueError):
        return {}
    return {row["ltGdsCd"]: row for row in (data.get("list", []) or [])}


def get_all_games_status() -> list[dict]:
    """7개 게임 각각의 실시간 잭팟 + 1등 당첨현황(이력·통계·확률)을 모아서 반환."""
    jackpots_by_prefix: dict[str, dict[str, dict]] = {}
    result = []
    for code, (name, category, prefix, info_path) in GAMES.items():
        if prefix not in jackpots_by_prefix:
            jackpots_by_prefix[prefix] = _fetch_jackpots(prefix)
        jackpot = jackpots_by_prefix[prefix].get(code, {})
        first_rank = _fetch_first_rank(code)
        history = first_rank["list"]
        info = first_rank["info"]
        predicted_date = _estimate_next_win_date(history)
        fallback_avg, fallback_max, fallback_min = _history_amount_stats(history)
        result.append(
            {
                "code": code,
                "name": name,
                "category": category,
                "rank1_jackpot": jackpot.get("rnk1JckpAmt"),
                "rank2_jackpot": jackpot.get("rnk2JckpAmt"),
                "total_wins": first_rank["total"],
                "recent_wins": history[:DISPLAY_COUNT],
                "avg_amount": info.get("ltWnAvg") or fallback_avg,
                "max_amount": info.get("ltWnMax") or fallback_max,
                "min_amount": info.get("ltWnMin") or fallback_min,
                "probability": _fetch_rank1_probability(code, info_path),
                "predicted_date": predicted_date,
                "predict_status": _predict_status(predicted_date),
            }
        )
    return result
