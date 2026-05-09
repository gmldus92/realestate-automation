"""급매 판별 — 문구 감지 + 평균 단가 대비 -20% 이탈"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crawlers.naver_land import Listing


def tag_urgent(listings: list["Listing"], settings: dict) -> list["Listing"]:
    threshold = settings["urgent_sale"]["price_discount_threshold"] / 100  # 0.20
    keyword = settings["urgent_sale"]["keyword"]

    # 지역 + 평형대별 평균 단가(만원/평) 계산
    bucket: dict[str, list[float]] = {}
    for l in listings:
        key = _bucket_key(l)
        ppp = l.price / l.area_pyeong if l.area_pyeong > 0 else 0
        bucket.setdefault(key, []).append(ppp)

    avg_ppp: dict[str, float] = {k: sum(v) / len(v) for k, v in bucket.items()}

    for l in listings:
        reasons = []

        # 조건 1: 매물 특징에 급매 문구 포함
        if keyword in l.description:
            reasons.append("매물특징 '급매' 문구")

        # 조건 2: 평균 단가 대비 -20% 이상
        key = _bucket_key(l)
        avg = avg_ppp.get(key, 0)
        if avg > 0:
            ppp = l.price / l.area_pyeong if l.area_pyeong > 0 else 0
            discount = (avg - ppp) / avg
            if discount >= threshold:
                reasons.append(f"평균단가 대비 -{discount*100:.0f}% 저렴")

        if reasons:
            l.is_urgent = True
            l.urgent_reason = " / ".join(reasons)

    return listings


def _bucket_key(l: "Listing") -> str:
    pyeong_band = int(l.area_pyeong // 3) * 3  # 3평 단위로 묶음
    return f"{l.region}_{pyeong_band}"
