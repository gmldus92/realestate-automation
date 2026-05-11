"""네이버 부동산 매물 크롤러 — 네트워크 인터셉트 방식"""
import asyncio
from dataclasses import dataclass, asdict

from playwright.async_api import async_playwright, Response


@dataclass
class Listing:
    id: str
    name: str
    price: int
    area_pyeong: float
    area_m2: float
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


async def fetch_listings(settings: dict) -> list[Listing]:
    price_min = settings["listing"]["price_min"]
    price_max = settings["listing"]["price_max"]
    area_min = settings["listing"]["area_min"]
    area_max = settings["listing"]["area_max"]
    regions = settings["listing"]["regions"]

    area_min_m2 = int(area_min * 3.305785)
    area_max_m2 = int(area_max * 3.305785)
    _ = regions  # settings에서 읽지만 인터셉트 방식에서는 URL 필터로 대체

    intercepted: list[dict] = []

    async def handle_response(response: Response) -> None:
        url = response.url
        if "land.naver.com" in url:
            print(f"[naver_land] 응답: {response.status} {url[:120]}")
        if "single-markers" not in url and "articleList" not in url:
            return
        if response.status != 200:
            return
        try:
            data = await response.json()
            if isinstance(data, list) and data:
                intercepted.extend(data)
                print(f"[naver_land] 인터셉트: {len(data)}개 단지")
            elif isinstance(data, dict):
                arts = data.get("body", {}).get("list", [])
                if arts:
                    intercepted.extend(arts)
                    print(f"[naver_land] 인터셉트: {len(arts)}개 매물")
        except Exception:
            pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        page.on("response", handle_response)

        search_url = (
            "https://new.land.naver.com/"
            f"?ms=37.55,127.0,10"
            f"&a=APT"
            f"&b=A1"
            f"&e=RETAIL"
            f"&f={price_min}"
            f"&g={price_max}"
            f"&h={area_min_m2}"
            f"&i={area_max_m2}"
        )
        print(f"[naver_land] 검색 페이지 로딩: {search_url}")
        try:
            await page.goto(search_url, wait_until="load", timeout=60000)
            await asyncio.sleep(15)
        except Exception as e:
            print(f"[naver_land] 페이지 로드 오류: {e}")

        print(f"[naver_land] 인터셉트 완료: 총 {len(intercepted)}개 항목")
        await browser.close()

    # 단지 데이터 → Listing 변환
    results: list[Listing] = []
    seen: set[str] = set()

    for item in intercepted:
        try:
            # 단지 마커인 경우 (complexNo 있음)
            cx_no = str(item.get("complexNo", item.get("markerId", "")))
            cx_name = item.get("complexName", item.get("atclNm", ""))

            # 매물 아이템인 경우
            article_no = str(item.get("articleNo", item.get("atclNo", cx_no)))
            if not article_no or article_no in seen:
                continue
            seen.add(article_no)

            price_raw = str(item.get("dealOrWarrantPrc", item.get("dealPrice", "0"))).replace(",", "")
            price = int(price_raw) if price_raw.isdigit() else 0
            area_m2 = float(item.get("area1", item.get("exclusiveArea", item.get("area", 0))) or 0)
            area_pyeong = round(area_m2 / 3.305785, 1)

            region = "서울" if any(
                r in item.get("cortarAddress", item.get("address", "")) for r in ["서울"]
            ) else "경기"

            results.append(Listing(
                id=article_no,
                name=cx_name,
                price=price,
                area_pyeong=area_pyeong,
                area_m2=area_m2,
                floor=str(item.get("flrInfo", item.get("floor", ""))),
                region=region,
                address=item.get("cortarAddress", item.get("address", "")),
                description=item.get("articleFeatureDescription", item.get("atclFetrDesc", "")),
                url=f"https://new.land.naver.com/complexes/{cx_no}#articleNo={article_no}",
            ))
        except Exception:
            continue

    print(f"[naver_land] 최종 매물: {len(results)}건")
    return results
