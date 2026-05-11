"""네이버 부동산 매물 크롤러 — fin.land.naver.com 인터셉트 방식"""
import asyncio
from dataclasses import dataclass, asdict

from playwright.async_api import async_playwright, Response

LAYER = "NobwRAlgJmBcYEMBOAXCBjANgUwPqYgGcUwAaMQ7ZdACwAVkEBbQucFATwAds4wBhAIJ0AygFUAMgFEyiVBhwiA9vIB2AcwAq3XvAAigzVNx6pI-mAC+lgLpA"

# (지역명, center값)
REGION_URLS = [
    ("광명 광명동",  "3zcqu4-2AI8xa"),
    ("광명 철산동",  "3zd2cM-2AItRK"),
    ("광명 하안동",  "3zdcS4-2AHtGU"),
    ("안양 안양동",  "3zfpss-2AEEq8"),
    ("안양 비산동",  "3zg8uS-2AF288"),
    ("안양 평촌동",  "3zhtTQ-2AECfs"),
    ("안양 호계동",  "3zgLfs-2AE5Zi"),
]


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


def _parse_price(raw) -> int:
    s = str(raw).replace(",", "").replace(" ", "").strip()
    if s.isdigit():
        return int(s)
    # "5억3000" 형태 처리
    result = 0
    if "억" in s:
        parts = s.split("억")
        result += int(parts[0]) * 10000
        s = parts[1]
    if s and s.isdigit():
        result += int(s)
    return result


async def fetch_listings(settings: dict) -> list[Listing]:
    price_min = settings["listing"]["price_min"]
    price_max = settings["listing"]["price_max"]
    area_min = settings["listing"]["area_min"]
    area_max = settings["listing"]["area_max"]

    intercepted: list[dict] = []

    async def handle_response(response: Response) -> None:
        url = response.url
        ct = response.headers.get("content-type", "")
        if "naver.com" in url and response.status == 200:
            print(f"[naver_land] 응답: {url[:150]} | ct={ct[:50]}")
        if "fin.land.naver.com" in url and response.status == 200 and "json" in ct:
            try:
                data = await response.json()
                if isinstance(data, list) and data:
                    intercepted.extend(data)
                elif isinstance(data, dict):
                    # 다양한 키 시도
                    for key in ("items", "list", "articleList", "complexList", "body"):
                        val = data.get(key)
                        if isinstance(val, list) and val:
                            intercepted.extend(val)
                            print(f"[naver_land] '{key}' 키에서 {len(val)}개 수집")
                            break
                        if isinstance(val, dict):
                            inner = val.get("list", val.get("items", []))
                            if inner:
                                intercepted.extend(inner)
                                print(f"[naver_land] '{key}.list' 에서 {len(inner)}개 수집")
                                break
            except Exception as e:
                print(f"[naver_land] 파싱 오류: {e}")

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

        for region_name, center in REGION_URLS:
            url = (
                f"https://fin.land.naver.com/map"
                f"?realEstateTypes=A01&tradeTypes=A1"
                f"&center={center}&zoom=14"
                f"&showOnlySelectedRegion=true"
                f"&layer={LAYER}"
            )
            print(f"[naver_land] 로딩: {region_name}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(8)
            except Exception as e:
                print(f"[naver_land] 로드 실패 ({region_name}): {e}")
                continue

        print(f"[naver_land] 인터셉트 완료: 총 {len(intercepted)}개 항목")
        await browser.close()

    # 가격·면적 필터 + Listing 변환
    results: list[Listing] = []
    seen: set[str] = set()

    for item in intercepted:
        try:
            price = _parse_price(
                item.get("dealOrWarrantPrc",
                item.get("price",
                item.get("dealPrice", 0)))
            )
            area_m2 = float(
                item.get("area1",
                item.get("exclusiveArea",
                item.get("area",
                item.get("supplyArea", 0)))) or 0
            )
            area_pyeong = round(area_m2 / 3.305785, 1)

            if not (price_min <= price <= price_max):
                continue
            if area_m2 > 0 and not (area_min * 3.305785 <= area_m2 <= area_max * 3.305785):
                continue

            article_no = str(
                item.get("articleNo",
                item.get("atclNo",
                item.get("id",
                item.get("complexNo", ""))))
            )
            if not article_no or article_no in seen:
                continue
            seen.add(article_no)

            cx_no = str(item.get("complexNo", item.get("markerId", "")))
            cx_name = str(item.get("complexName", item.get("atclNm", item.get("name", ""))))
            address = item.get("cortarAddress", item.get("address", item.get("roadAddress", "")))
            region = "서울" if "서울" in address else "경기"

            results.append(Listing(
                id=article_no,
                name=cx_name,
                price=price,
                area_pyeong=area_pyeong,
                area_m2=area_m2,
                floor=str(item.get("flrInfo", item.get("floor", item.get("floorInfo", "")))),
                region=region,
                address=address,
                description=item.get("articleFeatureDescription", item.get("atclFetrDesc", item.get("description", ""))),
                url=f"https://fin.land.naver.com/complexes/{cx_no}" if cx_no else f"https://fin.land.naver.com/",
            ))
        except Exception:
            continue

    print(f"[naver_land] 최종 매물: {len(results)}건")
    return results
