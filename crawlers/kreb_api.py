"""한국부동산원 실거래가 — 공공데이터포털 공식 API"""
import os
import asyncio
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

import aiohttp

API_KEY = os.environ.get("KREB_API_KEY", "")
BASE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"


@dataclass
class Transaction:
    complex_name: str
    area_m2: float
    floor: int
    deal_amount: int   # 만원
    deal_year: int
    deal_month: int
    deal_day: int
    region_code: str

    @property
    def deal_date(self) -> str:
        return f"{self.deal_year}-{self.deal_month:02d}-{self.deal_day:02d}"

    @property
    def price_per_pyeong(self) -> int:
        pyeong = self.area_m2 / 3.305785
        return int(self.deal_amount / pyeong) if pyeong > 0 else 0


async def fetch_transactions(region_code: str, yyyymm: str) -> list[Transaction]:
    """region_code: 법정동 코드 앞 5자리, yyyymm: '202504' 형식"""
    if not API_KEY:
        print("[kreb_api] KREB_API_KEY 환경변수가 설정되지 않았습니다.")
        return []

    params = {
        "serviceKey": API_KEY,
        "LAWD_CD": region_code,
        "DEAL_YMD": yyyymm,
        "numOfRows": 1000,
        "pageNo": 1,
    }

    results: list[Transaction] = []

    timeout = aiohttp.ClientTimeout(total=30, connect=10)
    text = ""
    for attempt in range(1, 4):
        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(BASE_URL, params=params) as resp:
                    text = await resp.text()
            break
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == 3:
                print(f"[kreb_api] {region_code}/{yyyymm} 요청 {attempt}회 실패, 포기: {e}")
                return []
            print(f"[kreb_api] {region_code}/{yyyymm} 요청 {attempt}회 실패, 재시도: {e}")
            await asyncio.sleep(2 ** attempt)

    try:
        root = ET.fromstring(text)
        items = root.findall(".//item")
        for item in items:
            def g(tag: str) -> str:
                el = item.find(tag)
                return el.text.strip() if el is not None and el.text else ""

            amount_raw = g("dealAmount").replace(",", "")
            results.append(Transaction(
                complex_name=g("aptNm"),
                area_m2=float(g("excluUseAr") or 0),
                floor=int(g("floor") or 0),
                deal_amount=int(amount_raw) if amount_raw.isdigit() else 0,
                deal_year=int(g("dealYear") or 0),
                deal_month=int(g("dealMonth") or 0),
                deal_day=int(g("dealDay") or 0),
                region_code=region_code,
            ))
    except ET.ParseError as e:
        print(f"[kreb_api] XML 파싱 오류: {e} | 응답 앞부분: {text[:300]}")

    return results


async def fetch_recent_transactions(complex_name: str, region_code: str, months: int = 6) -> list[Transaction]:
    """최근 N개월 실거래가 수집"""
    now = datetime.now()
    tasks = []
    for i in range(months):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        tasks.append(fetch_transactions(region_code, f"{y}{m:02d}"))

    all_results = []
    for task in tasks:
        batch = await task
        all_results.extend(batch)
        await asyncio.sleep(0.5)

    return [t for t in all_results if complex_name in t.complex_name]
