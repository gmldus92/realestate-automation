"""네이버 부동산 매물 크롤러 (Playwright 기반 — 셀프 호스팅 러너용)"""
import asyncio
import json
from dataclasses import dataclass, asdict

from playwright.async_api import async_playwright


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
    description: str
    url: str
    is_new: bool = False
    is_urgent: bool = False
    urgent_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


_BASE_URL = "https://m.land.naver.com/cluster/ajax/articleList"

_REGION_CODES = {
    "서울": "1100000000",
    "경기": "4100000000",
}

_APT_TYPE = "APT"


async def fetch_listings(settings: dict) -> list[Listing]:
    price_min = settings["listing"]["price_min"]
    price_max = settings["listing"]["price_max"]
    area_min = settings["listing"]["area_min"]
    area_max = settings["listing"]["area_max"]
    regions = settings["listing"]["regions"]

    results: list[Listing] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
            )
        )
        page = await context.new_page()

        for region in regions:
            region_code = _REGION_CODES.get(region)
            if not region_code:
                continue

            page_no = 1
            while True:
                params = {
                    "rletTpCd": _APT_TYPE,
                    "tradTpCd": "A1",
                    "cortarNo": region_code,
                    "page": page_no,
                    "sameAddressGroup": "false",
                    "priceMin": price_min,
                    "priceMax": price_max,
                    "areaMin": int(area_min * 3.305785),
                    "areaMax": int(area_max * 3.305785),
                }
                query = "&".join(f"{k}={v}" for k, v in params.items())
                url = f"{_BASE_URL}?{query}"

                try:
                    await page.goto(url, wait_until="networkidle", timeout=60000)
                except Exception as e:
                    print(f"[naver_land] 페이지 로드 실패: {e}")
                    break
                raw = await page.inner_text("body")

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    break

                articles = data.get("body", {}).get("list", [])
                if not articles:
                    break

                for art in articles:
                    try:
                        price_raw = art.get("dealOrWarrantPrc", "0").replace(",", "")
                        price = int(price_raw) if price_raw.isdigit() else 0
                        area_m2 = float(art.get("area1", 0))
                        area_pyeong = round(area_m2 / 3.305785, 1)

                        listing = Listing(
                            id=art.get("atclNo", ""),
                            name=art.get("atclNm", ""),
                            price=price,
                            area_pyeong=area_pyeong,
                            area_m2=area_m2,
                            floor=art.get("flrInfo", ""),
                            region=region,
                            address=art.get("cortarAddress", ""),
                            description=art.get("atclFetrDesc", ""),
                            url=f"https://m.land.naver.com/article/info/{art.get('atclNo', '')}",
                        )
                        results.append(listing)
                    except (ValueError, KeyError):
                        continue

                total_pages = data.get("body", {}).get("totalPage", 1)
                print(f"[naver_land] {region} 페이지 {page_no}/{total_pages}: {len(articles)}건")
                if page_no >= total_pages:
                    break
                page_no += 1
                await asyncio.sleep(0.5)

        await browser.close()

    seen: set[str] = set()
    unique = [l for l in results if l.id not in seen and not seen.add(l.id)]  # type: ignore[func-returns-value]
    print(f"[naver_land] 최종 매물: {len(unique)}건")
    return unique
