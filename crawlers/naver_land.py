"""네이버 부동산 매물 크롤러 (Playwright + page.evaluate fetch — 셀프 호스팅 러너용)"""
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


# (bottomLat, topLat, leftLon, rightLon, region_label)
REGION_TILES = [
    (37.43, 37.57, 126.76, 126.97, "서울"),
    (37.43, 37.57, 126.97, 127.18, "서울"),
    (37.57, 37.71, 126.76, 126.97, "서울"),
    (37.57, 37.71, 126.97, 127.18, "서울"),
    (37.38, 37.56, 126.76, 126.97, "경기"),
    (37.20, 37.45, 126.97, 127.25, "경기"),
    (37.55, 37.75, 126.74, 126.97, "경기"),
    (37.55, 37.75, 126.97, 127.35, "경기"),
]


async def _fetch_via_evaluate(page, path: str, params: dict):
    """page.evaluate()로 same-origin fetch — 쿠키 자동 포함"""
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{path}?{query}"
    try:
        result = await page.evaluate(f"""
            async () => {{
                const resp = await fetch('{url}', {{
                    headers: {{
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'Referer': 'https://new.land.naver.com/'
                    }}
                }});
                const text = await resp.text();
                try {{ return JSON.parse(text); }} catch(e) {{ return null; }}
            }}
        """)
        return result
    except Exception as e:
        print(f"[naver_land] evaluate 오류: {e}")
        return None


async def fetch_listings(settings: dict) -> list[Listing]:
    price_min = settings["listing"]["price_min"]
    price_max = settings["listing"]["price_max"]
    area_min = settings["listing"]["area_min"]
    area_max = settings["listing"]["area_max"]
    regions = settings["listing"]["regions"]

    area_min_m2 = int(area_min * 3.305785)
    area_max_m2 = int(area_max * 3.305785)

    results: list[Listing] = []
    seen_complex: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        # new.land.naver.com 세션 확립 (JS 쿠키 획득)
        print("[naver_land] new.land.naver.com 로딩 중...")
        try:
            await page.goto(
                "https://new.land.naver.com/",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await asyncio.sleep(3)  # JS 쿠키 세팅 대기
            print("[naver_land] 세션 확립 완료")
        except Exception as e:
            print(f"[naver_land] 메인 페이지 로드 실패: {e}")

        for tile in REGION_TILES:
            bottom_lat, top_lat, left_lon, right_lon, region_label = tile
            if region_label not in regions:
                continue

            # 단지 목록 조회
            complex_params = {
                "zoom": 13,
                "priceType": "RETAIL",
                "realEstateType": "APT:PRE:ABYG:JGC",
                "tradeType": "A1",
                "priceMin": price_min,
                "priceMax": price_max,
                "areaMin": area_min_m2,
                "areaMax": area_max_m2,
                "showArticle": "false",
                "sameAddressGroup": "false",
                "leftLon": left_lon,
                "rightLon": right_lon,
                "topLat": top_lat,
                "bottomLat": bottom_lat,
                "isPresale": "true",
            }
            complexes = await _fetch_via_evaluate(
                page, "/api/complexes/single-markers/2.0", complex_params
            )
            if not isinstance(complexes, list):
                print(f"[naver_land] {region_label} 단지 응답 이상: {str(complexes)[:100]}")
                continue

            print(f"[naver_land] {region_label} ({bottom_lat}~{top_lat}): 단지 {len(complexes)}개")

            for cx in complexes:
                cx_no = str(cx.get("complexNo", cx.get("markerId", "")))
                cx_name = cx.get("complexName", "")
                if not cx_no or cx_no in seen_complex:
                    continue
                seen_complex.add(cx_no)

                article_params = {
                    "tradeType": "A1",
                    "priceMin": price_min,
                    "priceMax": price_max,
                    "areaMin": area_min_m2,
                    "areaMax": area_max_m2,
                }
                arts_data = await _fetch_via_evaluate(
                    page, f"/api/articles/complex/{cx_no}", article_params
                )

                articles = []
                if isinstance(arts_data, list):
                    articles = arts_data
                elif isinstance(arts_data, dict):
                    for key in ("articleList", "list", "body"):
                        val = arts_data.get(key)
                        if isinstance(val, list):
                            articles = val
                            break
                        if isinstance(val, dict):
                            articles = val.get("list", [])
                            break

                for art in articles:
                    try:
                        price_raw = str(art.get("dealOrWarrantPrc", art.get("dealPrice", "0"))).replace(",", "")
                        price = int(price_raw) if price_raw.isdigit() else 0
                        area_m2 = float(art.get("area1", art.get("exclusiveArea", art.get("area", 0))) or 0)
                        area_pyeong = round(area_m2 / 3.305785, 1)
                        article_no = str(art.get("articleNo", art.get("atclNo", "")))
                        results.append(Listing(
                            id=article_no,
                            name=art.get("complexName", art.get("atclNm", cx_name)),
                            price=price,
                            area_pyeong=area_pyeong,
                            area_m2=area_m2,
                            floor=str(art.get("flrInfo", art.get("floor", ""))),
                            region=region_label,
                            address=art.get("cortarAddress", art.get("address", "")),
                            description=art.get("articleFeatureDescription", art.get("atclFetrDesc", "")),
                            url=f"https://new.land.naver.com/complexes/{cx_no}#articleNo={article_no}",
                        ))
                    except Exception:
                        continue

                await asyncio.sleep(0.1)

            await asyncio.sleep(0.5)

        await browser.close()

    seen: set[str] = set()
    unique = [l for l in results if l.id not in seen and not seen.add(l.id)]  # type: ignore[func-returns-value]
    print(f"[naver_land] 최종 매물: {len(unique)}건")
    return unique
