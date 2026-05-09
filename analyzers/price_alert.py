"""가격 변동 알림 — 즐겨찾기 단지 실거래가가 임계값 이상 변동 시 즉시 알림"""
from __future__ import annotations
import json
from pathlib import Path

PRICE_HISTORY_FILE = Path(__file__).parent.parent / "data" / "price_history.json"


def check_alerts(
    complex_name: str,
    transactions: list,
    threshold_pct: float,
) -> list[dict]:
    """최근 거래가와 이전 거래가를 비교해 임계값 초과 시 alert 반환"""
    if len(transactions) < 2:
        return []

    history = _load_history()
    prev_price = history.get(complex_name)

    sorted_txns = sorted(
        transactions,
        key=lambda t: (t.deal_year, t.deal_month, t.deal_day),
        reverse=True,
    )
    latest_price = sorted_txns[0].deal_amount

    alerts = []
    if prev_price and prev_price > 0:
        change_pct = abs(latest_price - prev_price) / prev_price * 100
        if change_pct >= threshold_pct:
            direction = "상승" if latest_price > prev_price else "하락"
            alerts.append({
                "complex_name": complex_name,
                "prev_price": prev_price,
                "new_price": latest_price,
                "change_pct": round(change_pct, 1),
                "direction": direction,
                "deal_date": sorted_txns[0].deal_date,
            })

    history[complex_name] = latest_price
    _save_history(history)

    return alerts


def _load_history() -> dict:
    if not PRICE_HISTORY_FILE.exists():
        return {}
    with open(PRICE_HISTORY_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_history(history: dict) -> None:
    PRICE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PRICE_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False)
