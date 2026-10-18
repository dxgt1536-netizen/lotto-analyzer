"""저장된 회차 데이터를 바탕으로 한 통계 분석 및 번호 추천."""

from __future__ import annotations

import random
from collections import Counter
from itertools import combinations

from lotto_data import get_all_draws

MAIN_RANGE = range(1, 46)


def _main_numbers(draw) -> list[int]:
    return [draw["n1"], draw["n2"], draw["n3"], draw["n4"], draw["n5"], draw["n6"]]


def number_frequency() -> dict[int, int]:
    counter = Counter()
    for draw in get_all_draws():
        counter.update(_main_numbers(draw))
    return {n: counter.get(n, 0) for n in MAIN_RANGE}


def recent_number_frequency(recent_n: int = 50) -> dict[int, int]:
    """가장 최근 recent_n회 회차만으로 집계한 번호별 출현 빈도."""
    counter = Counter()
    for draw in get_all_draws()[:recent_n]:  # get_all_draws()는 최신 회차부터 내림차순
        counter.update(_main_numbers(draw))
    return {n: counter.get(n, 0) for n in MAIN_RANGE}


def bonus_frequency() -> dict[int, int]:
    counter = Counter(draw["bonus"] for draw in get_all_draws())
    return {n: counter.get(n, 0) for n in MAIN_RANGE}


def hot_cold_numbers(
    top_n: int = 6, freq: dict[int, int] | None = None, max_n: int = 8
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """상위/하위 top_n개를 뽑되, top_n번째와 횟수가 동점인 번호가 더 있으면
    max_n개까지 늘려서 같이 보여준다 (동점자를 임의로 잘라내지 않기 위함)."""
    freq = freq if freq is not None else number_frequency()
    desc = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    asc = sorted(freq.items(), key=lambda kv: (kv[1], kv[0]))
    hot = _top_with_ties(desc, top_n, max_n)
    cold = _top_with_ties(asc, top_n, max_n)
    return hot, cold


def _top_with_ties(
    ranked: list[tuple[int, int]], top_n: int, max_n: int
) -> list[tuple[int, int]]:
    if len(ranked) <= top_n:
        return ranked[:top_n]
    result = ranked[:top_n]
    cutoff = ranked[top_n - 1][1]
    i = top_n
    while i < len(ranked) and len(result) < max_n and ranked[i][1] == cutoff:
        result.append(ranked[i])
        i += 1
    return result

def odd_even_ratio() -> dict[str, int]:
    odd = even = 0
    for draw in get_all_draws():
        for n in _main_numbers(draw):
            if n % 2 == 0:
                even += 1
            else:
                odd += 1
    return {"odd": odd, "even": even}


def low_high_ratio(threshold: int = 23) -> dict[str, int]:
    low = high = 0
    for draw in get_all_draws():
        for n in _main_numbers(draw):
            if n < threshold:
                low += 1
            else:
                high += 1
    return {"low": low, "high": high}


def sum_distribution_curve(
    bucket_size: int = 5, width: int = 640, height: int = 180, pad: int = 20
) -> dict:
    """당첨번호 합계 분포를 부드러운 곡선(카트멀롬 스플라인) SVG 경로로 만든다.

    6개 번호 합은 중심극한정리로 종 모양에 가까운 분포를 이루므로, 막대 대신
    곡선으로 그리면 그 모양이 더 잘 드러난다. 좌표는 SVG viewBox 기준으로 미리 계산해
    템플릿에서는 <path d="..."> 에 그대로 꽂기만 하면 되게 한다.
    """
    sums = [sum(_main_numbers(d)) for d in get_all_draws()]
    if not sums:
        return {
            "area_path": "", "line_path": "", "points": [], "x_ticks": [],
            "width": width, "height": height, "baseline_y": height - pad,
        }

    counter: Counter[int] = Counter()
    for s in sums:
        counter[(s // bucket_size) * bucket_size] += 1

    min_b, max_b = min(counter), max(counter)
    buckets = list(range(min_b, max_b + bucket_size, bucket_size))
    counts = [counter.get(b, 0) for b in buckets]
    max_count = max(counts) if counts else 0

    plot_w = width - 2 * pad
    plot_h = height - 2 * pad
    n = len(buckets)
    baseline_y = pad + plot_h

    def sx(i: int) -> float:
        return pad + (i / (n - 1)) * plot_w if n > 1 else width / 2

    def sy(c: int) -> float:
        return baseline_y - (c / max_count * plot_h if max_count else 0)

    coords = [(sx(i), sy(counts[i])) for i in range(n)]
    line_path = _catmull_rom_path(coords)
    area_path = (
        f"{line_path} L {coords[-1][0]:.1f},{baseline_y:.1f} "
        f"L {coords[0][0]:.1f},{baseline_y:.1f} Z"
        if coords else ""
    )

    tick_count = min(6, n)
    x_ticks = []
    if n > 1 and tick_count > 1:
        for i in range(tick_count):
            idx = round(i * (n - 1) / (tick_count - 1))
            x_ticks.append({"x": coords[idx][0], "label": buckets[idx]})

    points = [
        {
            "x": coords[i][0],
            "y": coords[i][1],
            "label": f"{buckets[i]}~{buckets[i] + bucket_size - 1}",
            "count": counts[i],
        }
        for i in range(n)
    ]

    return {
        "area_path": area_path,
        "line_path": line_path,
        "points": points,
        "x_ticks": x_ticks,
        "width": width,
        "height": height,
        "baseline_y": baseline_y,
    }


def _catmull_rom_path(pts: list[tuple[float, float]]) -> str:
    """점들을 지나는 부드러운 곡선의 SVG path 'd' 문자열 (균일 카트멀롬 -> 3차 베지어 변환)."""
    if not pts:
        return ""
    if len(pts) == 1:
        x, y = pts[0]
        return f"M {x:.1f},{y:.1f}"

    def get(i: int) -> tuple[float, float]:
        return pts[max(0, min(len(pts) - 1, i))]

    d = f"M {pts[0][0]:.1f},{pts[0][1]:.1f} "
    for i in range(len(pts) - 1):
        p0, p1, p2, p3 = get(i - 1), get(i), get(i + 1), get(i + 2)
        c1x, c1y = p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6
        c2x, c2y = p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6
        d += f"C {c1x:.1f},{c1y:.1f} {c2x:.1f},{c2y:.1f} {p2[0]:.1f},{p2[1]:.1f} "
    return d.strip()


def top_pairs(top_n: int = 10) -> list[tuple[tuple[int, int], int]]:
    counter = Counter()
    for draw in get_all_draws():
        for pair in combinations(sorted(_main_numbers(draw)), 2):
            counter[pair] += 1
    return counter.most_common(top_n)


def recent_draws(limit: int = 10):
    return get_all_draws()[:limit]


def random_pick(count: int = 5) -> list[list[int]]:
    return [sorted(random.sample(MAIN_RANGE, 6)) for _ in range(count)]


def hot_pick(count: int = 5) -> list[list[int]]:
    """과거 출현 빈도가 높을수록 더 잘 뽑히는 가중치로 (복원 없는) 추첨."""
    freq = number_frequency()
    weights = {n: freq[n] + 1 for n in MAIN_RANGE}  # +1로 0빈도 번호도 선택 가능하게
    return [_weighted_sample(weights) for _ in range(count)]


def cold_pick(count: int = 5) -> list[list[int]]:
    """과거 출현 빈도가 낮을수록 더 잘 뽑히는 가중치로 (복원 없는) 추첨."""
    freq = number_frequency()
    max_freq = max(freq.values()) if freq else 0
    weights = {n: (max_freq - freq[n]) + 1 for n in MAIN_RANGE}
    return [_weighted_sample(weights) for _ in range(count)]


def _weighted_sample(weights: dict[int, int]) -> list[int]:
    pool = list(MAIN_RANGE)
    w = [weights[n] for n in pool]
    picked: list[int] = []
    for _ in range(6):
        chosen = random.choices(pool, weights=w, k=1)[0]
        idx = pool.index(chosen)
        picked.append(pool.pop(idx))
        w.pop(idx)
    return sorted(picked)
