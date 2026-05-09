"""KB부동산 시세 크롤러"""
import asyncio
from dataclasses import dataclass

from playwright.async_api import async_playwright


@dataclass
class KBTransaction:
    complex_name: str
    area_m2: float
    price_high: int   # 상위평균가 (만원)
    price_mid: int    # 일반평균가 (만원)
    price_low: int    # 하위평균가 (만원)
    updated_date: str
    source: str = "KB부동산"

    @property
    def price_per_pyeong(self) -> int:
        pyeong = self.area_m2 / 3.305785
        return int(self.price_mid / pyeong) if pyeong > 0 else 0


async def fetch_price(complex_name: str) -> list[KBTransaction]:
    results: list[KBTransaction] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        search_url = f"https://kbland.kr/map?아파트={complex_name}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # 검색창에 단지명 입력
        search_input = page.locator("input[placeholder*='단지'], input[placeholder*='검색']").first
        if await search_input.count() > 0:
            await search_input.fill(complex_name)
            await page.keyboard.press("Enter")
            await asyncio.sleep(2)

        # 시세 정보 파싱
        price_items = await page.locator(".price-item, .sise-item, [class*='price']").all()
        for item in price_items[:5]:
            try:
                text = await item.inner_text()
                if "만원" in text or "억" in text:
                    results.append(KBTransaction(
                        complex_name=complex_name,
                        area_m2=0.0,
                        price_high=0,
                        price_mid=_parse_price(text),
                        price_low=0,
                        updated_date="",
                    ))
            except Exception:
                continue

        await browser.close()

    return results


def _parse_price(text: str) -> int:
    import re
    text = text.replace(",", "").replace(" ", "")
    match = re.search(r"(\d+)억?(\d+)?", text)
    if not match:
        return 0
    eok = int(match.group(1))
    man = int(match.group(2) or 0)
    return eok * 10000 + man
