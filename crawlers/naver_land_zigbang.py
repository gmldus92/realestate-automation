"""직방 비공식 API 기반 아파트 매물 크롤러"""
import asyncio
from dataclasses import dataclass, asdict

import aiohttp
import pygeohash as geohash

ZIGBANG_SEARCH_URL = "https://apis.zigbang.com/v2/search"
ZIGBANG_ITEMS_URL  = "https://apis.zigbang.com/v2/items"
ZIGBANG_LIST_URL   = "https://apis.zigbang.com/v2/items/list"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.zigbang.com/",
    "Origin": "https://www.zigbang.com",
}

# 서울/경기 주요 지역 좌표 (geohash precision=5 기준 ~2.4km 반경)
REGION_COORDS = {
    "서울 강남": (37.5172, 127.0473),
    "서울 강서": (37.5509, 126.8496),
    "서울 마포": (37.5665, 126.9014),
    "서울 강동": (37.5301, 127.1238),
    "서울 노원": (37.6542, 127.0568),
    "서울 영등포": (37.5264, 126.8963),
    "서울 동작": (37.5124, 126.9393),
    "서울 관악": (37.4784, 126.9516),
    "서울 서초": (37.4837, 127.0324),
    "서울 송파": (37.5145, 127.1059),
    "경기 성남": (37.4200, 127.1269),
    "경기 수원": (37.2636, 127.0286),
    "경기 용인": (37.2411, 127.1776),
    "경기 고양": (37.6584, 126.8320),
    "경기 안양": (37.3943, 126.9568),
    "경기 광명": (37.4786, 126.8645),
    "경기 부천": (37.5034, 126.7660),
    "경기 의정부": (37.7381, 127.0338),
    "경기 남양주": (37.6360, 127.2165),
    "경기 하남": (37.5395, 127.2149),
}


@dataclass
class Listing:
    id: str
    name: str           # 단지명
    price: int          # 만원
    area_pyeong: float  # 평형
    area_m2: float      # 전용면적 m²
    floor: str
    region: str
    address: str
    description: str    # 매물 특징
    url: str
    is_new: bool = False
    is_urgent: bool = False
    urgent_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


async def _get_item_ids(session: aiohttp.ClientSession, gh: str, price_min: int, price_max: int) -> list[int]:
    """geohash 기준 매물 ID 목록 조회"""
    params = {
        "domain": "zigbang",
        "geohash": gh,
        "sales_type_in": "매매",
        "service_type_eq": "아파트",
        "sales_price_gteq": price_min * 10000,   # 만원 → 원
        "sales_price_lteq": price_max * 10000,
    }
    try:
        async with session.get(ZIGBANG_ITEMS_URL, params=params, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return [item["item_id"] for item in data.get("items", []) if "item_id" in item]
    except Exception as e:
        print(f"[zigbang] ID 조회 실패 ({gh}): {e}")
        return []


async def _get_item_details(session: aiohttp.ClientSession, item_ids: list[int]) -> list[dict]:
    """매물 ID 목록으로 상세 정보 조회 (100개씩 청크)"""
    results = []
    for i in range(0, len(item_ids), 100):
        chunk = item_ids[i:i+100]
        payload = {"domain": "zigbang", "item_ids": chunk, "withCoalition": True}
        try:
            async with session.post(ZIGBANG_LIST_URL, json=payload, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                results.extend(data.get("items", []))
        except Exception as e:
            print(f"[zigbang] 상세 조회 실패: {e}")
        await asyncio.sleep(0.3)
    return results


def _parse_listing(item: dict, region: str) -> Listing | None:
    try:
        area_m2 = float(item.get("전용면적", item.get("area", 0)) or 0)
        area_pyeong = round(area_m2 / 3.305785, 1) if area_m2 else 0

        price_raw = item.get("salesPrice", item.get("price", 0)) or 0
        price_man = int(price_raw) // 10000  # 원 → 만원

        item_id = str(item.get("itemId", item.get("item_id", "")))

        return Listing(
            id=item_id,
            name=item.get("complexName", item.get("buildingName", "")),
            price=price_man,
            area_pyeong=area_pyeong,
            area_m2=area_m2,
            floor=str(item.get("floor", "")),
            region=region,
            address=item.get("address", ""),
            description=item.get("description", item.get("detailedDescription", "")),
            url=f"https://www.zigbang.com/home/apt/items/{item_id}",
        )
    except Exception:
        return None


async def fetch_listings(settings: dict) -> list[Listing]:
    price_min = settings["listing"]["price_min"]
    price_max = settings["listing"]["price_max"]
    area_min  = settings["listing"]["area_min"]
    area_max  = settings["listing"]["area_max"]
    regions   = settings["listing"]["regions"]

    results: list[Listing] = []

    async with aiohttp.ClientSession() as session:
        for region_name, (lat, lng) in REGION_COORDS.items():
            region_prefix = region_name.split()[0]  # "서울" or "경기"
            if region_prefix not in regions:
                continue

            gh = geohash.encode(lat, lng, precision=5)
            item_ids = await _get_item_ids(session, gh, price_min, price_max)
            if not item_ids:
                await asyncio.sleep(0.3)
                continue

            print(f"[zigbang] {region_name}: {len(item_ids)}건 조회")
            items = await _get_item_details(session, item_ids)

            for item in items:
                listing = _parse_listing(item, region_name)
                if not listing:
                    continue
                # 평형 필터
                if not (area_min <= listing.area_pyeong <= area_max):
                    continue
                results.append(listing)

            await asyncio.sleep(0.5)

    # 중복 제거
    seen = set()
    unique = []
    for l in results:
        if l.id not in seen:
            seen.add(l.id)
            unique.append(l)

    print(f"[zigbang] 최종 매물: {len(unique)}건")
    return unique
