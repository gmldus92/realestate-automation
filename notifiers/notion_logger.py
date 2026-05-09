"""Notion API — 일자별 로그를 부동산 자동화 로그 DB에 저장"""
import os
from datetime import date

import requests

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_PARENT_PAGE_ID = os.environ.get("NOTION_PARENT_PAGE_ID", "")
NOTION_DB_ID_FILE = "data/notion_db_id.txt"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


def _get_or_create_db() -> str:
    """DB가 없으면 생성 후 ID 반환, 있으면 저장된 ID 반환"""
    from pathlib import Path
    db_id_path = Path(NOTION_DB_ID_FILE)
    if db_id_path.exists():
        return db_id_path.read_text().strip()

    if not NOTION_PARENT_PAGE_ID:
        print("[notion] NOTION_PARENT_PAGE_ID 환경변수가 설정되지 않았습니다.")
        return ""

    payload = {
        "parent": {"type": "page_id", "page_id": NOTION_PARENT_PAGE_ID},
        "title": [{"type": "text", "text": {"content": "부동산 자동화 로그"}}],
        "properties": {
            "날짜": {"date": {}},
            "매물수": {"number": {}},
            "신규매물": {"number": {}},
            "급매수": {"number": {}},
            "리포트URL": {"url": {}},
            "유튜브언급TOP3": {"rich_text": {}},
            "가격알림발생": {"checkbox": {}},
            "즐겨찾기단지요약": {"rich_text": {}},
        },
    }

    resp = requests.post("https://api.notion.com/v1/databases", headers=HEADERS, json=payload)
    if resp.status_code != 200:
        print(f"[notion] DB 생성 실패: {resp.text}")
        return ""

    db_id = resp.json()["id"]
    db_id_path.parent.mkdir(parents=True, exist_ok=True)
    db_id_path.write_text(db_id)
    print(f"[notion] DB 생성 완료: {db_id}")
    return db_id


def log(
    total_count: int,
    new_count: int,
    urgent_count: int,
    report_url: str,
    youtube_top3: str,
    price_alert: bool,
    favorites_summary: str,
) -> None:
    if not NOTION_TOKEN:
        print("[notion] NOTION_TOKEN 환경변수가 설정되지 않았습니다.")
        return

    db_id = _get_or_create_db()
    if not db_id:
        return

    today = date.today().isoformat()

    payload = {
        "parent": {"database_id": db_id},
        "properties": {
            "날짜": {"date": {"start": today}},
            "매물수": {"number": total_count},
            "신규매물": {"number": new_count},
            "급매수": {"number": urgent_count},
            "리포트URL": {"url": report_url or None},
            "유튜브언급TOP3": {"rich_text": [{"text": {"content": youtube_top3[:2000]}}]},
            "가격알림발생": {"checkbox": price_alert},
            "즐겨찾기단지요약": {"rich_text": [{"text": {"content": favorites_summary[:2000]}}]},
        },
    }

    resp = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=payload)
    if resp.status_code == 200:
        print(f"[notion] 로그 저장 완료: {today}")
    else:
        print(f"[notion] 로그 저장 실패: {resp.text}")
