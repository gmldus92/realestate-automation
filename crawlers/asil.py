"""아실(asil.kr) 실거래가 크롤러"""
import asyncio
from dataclasses import dataclass

from playwright.async_api import async_playwright


@dataclass
class AsilTransaction:
    complex_name: str
    area_m2: float
    floor: str
    price: int       # 만원
    deal_date: str
    source: str = "아실"

    @property
    def price_per_pyeong(self) -> int:
        pyeong = self.area_m2 / 3.305785
        return int(self.price / pyeong) if pyeong > 0 else 0


async def fetch_transactions(complex_name: str) -> list[AsilTransaction]:
    results: list[AsilTransaction] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        search_url = f"https://asil.kr/asil/complex/list.jsp?name={complex_name}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # 첫 번째 결과 클릭
        first_result = page.locator(".complex-item").first
        if await first_result.count() == 0:
            await browser.close()
            return results

        await first_result.click()
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2)

        # 실거래가 탭 클릭
        trade_tab = page.locator("a:has-text('실거래')")
        if await trade_tab.count() > 0:
            await trade_tab.first.click()
            await asyncio.sleep(2)

        rows = await page.locator(".trade-list-item, .deal-item, tr.trade-row").all()
        for row in rows:
            try:
                text = await row.inner_text()
                parts = [p.strip() for p in text.split("\n") if p.strip()]
                if len(parts) >= 3:
                    results.append(AsilTransaction(
                        complex_name=complex_name,
                        area_m2=0.0,
                        floor=parts[1] if len(parts) > 1 else "",
                        price=_parse_price(parts[0]),
                        deal_date=parts[-1] if parts else "",
                    ))
            except Exception:
                continue

        await browser.close()

    return results


def _parse_price(text: str) -> int:
    text = text.replace(",", "").replace(" ", "")
    import re
    match = re.search(r"(\d+)억?(\d+)?", text)
    if not match:
        return 0
    eok = int(match.group(1))
    man = int(match.group(2) or 0)
    return eok * 10000 + man
