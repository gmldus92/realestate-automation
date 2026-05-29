"""최고가 / 최저가 / 평균가 선 그래프 생성 (plotly → HTML + PNG)"""
from __future__ import annotations
import base64
from collections import defaultdict
from datetime import date as Date
from pathlib import Path

import plotly.graph_objects as go


def _group(transactions: list, unit: str) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for t in transactions:
        if t.deal_amount <= 0:
            continue
        if unit == "일":
            key = f"{t.deal_year}-{t.deal_month:02d}-{t.deal_day:02d}"
        elif unit == "주":
            d = Date(t.deal_year, t.deal_month, t.deal_day)
            key = f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
        else:
            key = f"{t.deal_year}-{t.deal_month:02d}"
        grouped[key].append(t.deal_amount)
    return grouped


def _make_figure(complex_name: str, grouped: dict, transactions: list) -> go.Figure:
    keys = sorted(grouped.keys())
    avgs = [int(sum(grouped[k]) / len(grouped[k])) for k in keys]

    # 모든 개별 거래가격 점
    all_dates = []
    all_prices = []
    for t in transactions:
        if t.deal_amount <= 0:
            continue
        all_dates.append(f"{t.deal_year}-{t.deal_month:02d}-{t.deal_day:02d}")
        all_prices.append(t.deal_amount)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=all_dates, y=all_prices, name="거래가격",
        mode="markers", marker=dict(color="#b2bec3", size=7, symbol="circle"),
    ))
    fig.add_trace(go.Scatter(
        x=keys, y=avgs, name="평균가",
        mode="lines+markers", line=dict(color="#3498db", width=2),
        marker=dict(color="#3498db", size=6),
    ))
    fig.update_layout(
        title=f"{complex_name} 실거래가 추이 (만원)",
        xaxis_title="날짜",
        yaxis_title="거래금액 (만원)",
        hovermode="x unified",
        template="plotly_white",
        legend=dict(orientation="h", y=-0.2),
        margin=dict(l=20, r=20, t=50, b=20),
        width=900, height=400,
    )
    return fig


def build_chart(complex_name: str, transactions: list, output_dir: Path, unit: str = "일") -> dict:
    """HTML(웹용) + base64 PNG(이메일용) 반환. 데이터 없으면 빈 dict."""
    from datetime import date as _date, timedelta
    cutoff = _date.today() - timedelta(days=90)
    transactions = [
        t for t in transactions
        if _date(t.deal_year, t.deal_month, t.deal_day) >= cutoff
    ]
    grouped = _group(transactions, unit)
    if not grouped:
        return {}

    fig = _make_figure(complex_name, grouped, transactions)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = complex_name.replace(" ", "_")

    # 웹 리포트용 HTML
    html_path = output_dir / f"chart_{safe_name}.html"
    fig.write_html(str(html_path), include_plotlyjs="cdn", full_html=False)
    html_snippet = html_path.read_text(encoding="utf-8")

    # 이메일용 PNG (base64)
    try:
        png_bytes = fig.to_image(format="png", scale=2)
        png_b64 = base64.b64encode(png_bytes).decode()
    except Exception:
        png_b64 = ""

    return {"name": complex_name, "html": html_snippet, "png_b64": png_b64}
