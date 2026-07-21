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


AREA_COLORS = ["#1456f0", "#ea5ec1", "#3daeff", "#e17055", "#00b894", "#fdcb6e"]


def _make_figure(complex_name: str, grouped: dict, transactions: list) -> go.Figure:
    keys = sorted(grouped.keys())
    avgs = [int(sum(grouped[k]) / len(grouped[k])) for k in keys]

    # 평형별로 그룹화
    area_groups: dict[float, list] = defaultdict(list)
    for t in transactions:
        if t.deal_amount <= 0:
            continue
        area_groups[round(t.area_m2, 1)].append(t)

    fig = go.Figure()

    # 평형별 색상 점
    for i, area_m2 in enumerate(sorted(area_groups.keys())):
        txs = area_groups[area_m2]
        color = AREA_COLORS[i % len(AREA_COLORS)]
        pyeong = area_m2 / 3.305785
        label = f"{pyeong:.0f}평 ({area_m2}㎡)"
        dates = [f"{t.deal_year}-{t.deal_month:02d}-{t.deal_day:02d}" for t in txs]
        prices = [t.deal_amount for t in txs]
        fig.add_trace(go.Scatter(
            x=dates, y=prices, name=label,
            mode="markers", marker=dict(color=color, size=9, symbol="circle"),
        ))

    # 전체 평균가 선
    fig.add_trace(go.Scatter(
        x=keys, y=avgs, name="평균가",
        mode="lines", line=dict(color="#636e72", width=1.5, dash="dot"),
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
