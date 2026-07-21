"""부동산 자동화 시스템 — 진입점"""
import asyncio
import argparse
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config_loader import load_settings, load_watchlist
from crawlers import kreb_api
from analyzers import price_alert, price_chart
from notifiers import gmail_sender, notion_logger

REPORT_DIR = Path("docs")  # GitHub Pages는 /docs 또는 gh-pages 브랜치
CHART_DIR = REPORT_DIR / "charts"
TEMPLATE_DIR = Path("report/templates")


async def run(dry_run: bool = False) -> None:
    today = date.today().isoformat()
    settings = load_settings()
    watchlist = load_watchlist()
    favorites = watchlist["favorites"]
    alert_threshold = watchlist["price_alert_threshold"]

    print(f"[main] 실행 시작: {today}")

    # ── 4. 즐겨찾기 단지 실거래가 수집 + 그래프 ────────────────────
    charts = []
    all_alerts = []
    favorites_summary_parts = []

    for fav in favorites:
        name = fav["name"]
        area = fav.get("area", "")
        # 행정구역 코드 — 안양=41171, 광명=41210 (앞 5자리)
        region_code_map = {
            "안양": "41171",
            "안양 만안": "41171",   # 만안구: 안양동·석수동·박달동
            "안양 동안": "41173",   # 동안구: 비산동·관양동·평촌동·호계동
            "안양 관양동": "41173", # 관양동 → 동안구
            "안양 비산": "41173",   # 비산동 → 동안구
            "안양 평촌": "41173",   # 평촌동 → 동안구
            "광명": "41210",
            "광명 철산": "41210",
            "광명 하안": "41210",
            "구로": "11530",
        }
        region_code = region_code_map.get(area, region_code_map.get(area.split()[0], "41171"))

        if dry_run:
            transactions = []
        else:
            print(f"[main] {name} 실거래가 수집 중...")
            transactions = await kreb_api.fetch_recent_transactions(name, region_code, months=6)

        # 그래프
        chart_unit = settings.get("report", {}).get("chart_unit", "일")
        filtered = [t for t in transactions if 42 <= t.area_m2 <= 70]
        if filtered:
            chart_data = price_chart.build_chart(name, filtered, CHART_DIR, unit=chart_unit)
            if chart_data:
                charts.append(chart_data)

            # 최신 실거래가 요약
            latest = max(transactions, key=lambda t: (t.deal_year, t.deal_month, t.deal_day))
            favorites_summary_parts.append(f"{name}: {latest.deal_amount:,}만원 ({latest.deal_date})")

        # 가격 변동 알림 체크
        alerts = price_alert.check_alerts(name, transactions, alert_threshold)
        all_alerts.extend(alerts)

    favorites_summary = " / ".join(favorites_summary_parts)

    # 단지별 최근 실거래가 5개씩
    trades_by_complex: dict[str, list] = {}
    for fav in favorites:
        name = fav["name"]
        area = fav.get("area", "")
        region_code_map = {
            "안양": "41171",
            "안양 만안": "41171",
            "안양 동안": "41173",
            "안양 관양동": "41173",
            "안양 비산": "41173",
            "안양 평촌": "41173",
            "광명": "41210",
            "광명 철산": "41210",
            "광명 하안": "41210",
            "구로": "11530",
        }
        region_code = region_code_map.get(area, region_code_map.get(area.split()[0], "41171"))
        if not dry_run:
            txs = await kreb_api.fetch_recent_transactions(name, region_code, months=6)
            trades_by_complex[name] = sorted(
                [t for t in txs if 42 <= t.area_m2 <= 70],
                key=lambda t: (t.deal_year, t.deal_month, t.deal_day),
                reverse=True,
            )[:5]

    # ── 5. 리포트 생성 ─────────────────────────────────────────────
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    report_template = env.get_template("report.html")
    render_args = dict(
        date=today,
        trades_by_complex=trades_by_complex,
        charts=charts,
    )
    report_html = report_template.render(**render_args, is_email=False)
    email_html = report_template.render(**render_args, is_email=True)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "index.html"
    report_path.write_text(report_html, encoding="utf-8")
    print(f"[main] 리포트 저장: {report_path}")

    # GitHub Pages URL (레포명 기준)
    repo_name = "realestate-automation"
    gh_pages_url = f"https://{{github_username}}.github.io/{repo_name}/"

    # ── 7. Gmail 발송 (월요일=0, 목요일=3) ────────────────────────
    is_send_day = datetime.now().weekday() in (0, 3)
    if not dry_run and is_send_day:
        gmail_sender.send_report(email_html, today)
    elif dry_run:
        print("[main] dry-run: 이메일 발송 건너뜀")
    else:
        print("[main] 오늘은 이메일 발송일이 아닙니다 (월/목만 발송)")

    # 가격 알림 즉시 발송 (요일 무관)
    price_alerted = False
    if all_alerts and not dry_run:
        price_alerted = True
        alert_template = env.get_template("alert.html")
        alert_html = alert_template.render(
            date=today,
            threshold=alert_threshold,
            alerts=all_alerts,
        )
        gmail_sender.send_alert(alert_html, today)
        print(f"[main] 가격 알림 발송: {len(all_alerts)}건")

    # ── 8. Notion 로그 저장 ────────────────────────────────────────
    notion_logger.log(
        report_url=gh_pages_url,
        price_alert=price_alerted,
        favorites_summary=favorites_summary,
    )

    print("[main] 완료")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="크롤링 없이 설정 파일 로드만 확인")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))
