"""부동산 자동화 시스템 — 진입점"""
import asyncio
import argparse
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config_loader import load_settings, load_channels, load_watchlist
from crawlers import naver_land, kreb_api
from analyzers import urgent_sale, new_listing, price_alert, price_chart, youtube_analysis
from report import map as map_builder
from notifiers import gmail_sender, notion_logger

REPORT_DIR = Path("docs")  # GitHub Pages는 /docs 또는 gh-pages 브랜치
CHART_DIR = REPORT_DIR / "charts"
TEMPLATE_DIR = Path("report/templates")


async def run(dry_run: bool = False) -> None:
    today = date.today().isoformat()
    settings = load_settings()
    channels = load_channels()
    watchlist = load_watchlist()
    favorites = watchlist["favorites"]
    watch_regions = watchlist["watch_regions"]
    alert_threshold = watchlist["price_alert_threshold"]

    print(f"[main] 실행 시작: {today}")

    # ── 1. 매물 크롤링 ─────────────────────────────────────────────
    if dry_run:
        print("[main] dry-run 모드: 크롤링 생략")
        listings = []
    else:
        print("[main] 직방 API 매물 수집 중...")
        listings = await naver_land.fetch_listings(settings)
        print(f"[main] 수집된 매물: {len(listings)}건")

    # ── 2. 신규 매물 감지 ──────────────────────────────────────────
    listings = new_listing.detect_new(listings)
    new_count = sum(1 for l in listings if l.is_new)
    print(f"[main] 신규 매물: {new_count}건")

    # ── 3. 급매 태그 ───────────────────────────────────────────────
    listings = urgent_sale.tag_urgent(listings, settings)
    urgent_listings = [l for l in listings if l.is_urgent]
    new_listings_only = [l for l in listings if l.is_new and not l.is_urgent]
    print(f"[main] 급매 매물: {len(urgent_listings)}건")

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
            "광명": "41210",
        }
        region_code = region_code_map.get(area.split()[0], "41171")

        if dry_run:
            transactions = []
        else:
            print(f"[main] {name} 실거래가 수집 중...")
            transactions = await kreb_api.fetch_recent_transactions(name, region_code, months=6)

        # 그래프
        chart_unit = settings.get("report", {}).get("chart_unit", "일")
        if transactions:
            chart_data = price_chart.build_chart(name, transactions, CHART_DIR, unit=chart_unit)
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
        region_code_map = {"안양": "41171", "광명": "41210"}
        region_code = region_code_map.get(area.split()[0], "41171")
        if not dry_run:
            txs = await kreb_api.fetch_recent_transactions(name, region_code, months=6)
            trades_by_complex[name] = sorted(
                txs,
                key=lambda t: (t.deal_year, t.deal_month, t.deal_day),
                reverse=True,
            )[:5]

    # ── 5. 유튜브 분석 ─────────────────────────────────────────────
    if dry_run:
        yt_summary = {}
    else:
        print("[main] 유튜브 채널 분석 중...")
        analyses = await youtube_analysis.analyze_channels(channels, watch_regions)
        yt_summary = youtube_analysis.summarize(analyses)
        print(f"[main] 분석된 영상: {yt_summary.get('total_videos', 0)}개")

    # ── 6. 리포트 생성 ─────────────────────────────────────────────
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    report_template = env.get_template("report.html")
    render_args = dict(
        date=today,
        trades_by_complex=trades_by_complex,
        charts=charts,
        youtube_summary=yt_summary,
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

    # ── 7. Gmail 발송 ──────────────────────────────────────────────
    gmail_sender.send_report(email_html, today)

    # 가격 알림 즉시 발송
    price_alerted = False
    if all_alerts:
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
    top3_str = ", ".join(
        f"{kw}({cnt})" for kw, cnt in yt_summary.get("keyword_ranking", [])[:3]
    )
    notion_logger.log(
        total_count=len(listings),
        new_count=new_count,
        urgent_count=len(urgent_listings),
        report_url=gh_pages_url,
        youtube_top3=top3_str,
        price_alert=price_alerted,
        favorites_summary=favorites_summary,
    )

    # ── 9. 전날 매물 ID 저장 (다음 실행을 위해) ────────────────────
    new_listing.save_current(listings)

    print(f"[main] 완료: 매물 {len(listings)}건 / 신규 {new_count}건 / 급매 {len(urgent_listings)}건")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="크롤링 없이 설정 파일 로드만 확인")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))
