"""신규 매물 감지 — 전날 매물 ID와 비교"""
from __future__ import annotations
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crawlers.naver_land import Listing

DATA_FILE = Path(__file__).parent.parent / "data" / "previous_listings.json"


def detect_new(listings: list["Listing"]) -> list["Listing"]:
    previous_ids = _load_previous()
    for l in listings:
        if l.id and l.id not in previous_ids:
            l.is_new = True
    return listings


def save_current(listings: list["Listing"]) -> None:
    ids = {l.id: True for l in listings if l.id}
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(ids, f)


def _load_previous() -> dict:
    if not DATA_FILE.exists():
        return {}
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)
