import asyncio
import logging
import re
from dataclasses import dataclass

import aiohttp
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}
_TIMEOUT = aiohttp.ClientTimeout(total=30)

_session: aiohttp.ClientSession | None = None


async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(headers=_HEADERS, timeout=_TIMEOUT)
    return _session


async def close_session() -> None:
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


@dataclass
class BankRate:
    bank: str
    buy: float | None
    sell: float | None


def _parse_rate_value(text: str) -> float | None:
    if not text:
        return None
    cleaned = text.strip().replace(",", ".").replace("\xa0", "").replace(" ", "")
    match = re.search(r"[\d]+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def extract_bank_rates_from_html(html: str) -> list[BankRate]:
    soup = BeautifulSoup(html, "lxml")
    rates: list[BankRate] = []

    containers = soup.select("div.currency-courses-offers-search-list__item")
    if not containers:
        containers = soup.select("[class*='currency-courses'] [class*='item']")

    for container in containers:
        bank_name_el = container.select_one(
            "[class*='bank-name'], [class*='bank_name'], .currencies-courses__bank"
        )
        if not bank_name_el:
            bank_name_el = container.select_one("a[href*='/bank/']")

        buy_el = container.select_one("[class*='buy'], [class*='purchase']")
        sell_el = container.select_one("[class*='sell'], [class*='sale']")

        if not sell_el:
            rate_cells = container.select("td")
            if len(rate_cells) >= 2:
                sell_el = rate_cells[-1]
                buy_el = rate_cells[-2]
            else:
                buy_el = None

        bank_name = bank_name_el.get_text(strip=True) if bank_name_el else None
        if not bank_name:
            continue

        buy_rate = _parse_rate_value(buy_el.get_text(strip=True)) if buy_el else None
        sell_rate = _parse_rate_value(sell_el.get_text(strip=True)) if sell_el else None

        rates.append(BankRate(bank=bank_name, buy=buy_rate, sell=sell_rate))

    if rates:
        return _deduplicate(rates)

    return _deduplicate(_extract_from_general_html(soup))


def _deduplicate(rates: list[BankRate]) -> list[BankRate]:
    seen: dict[str, BankRate] = {}
    for r in rates:
        key = r.bank.strip().lower()
        if key not in seen:
            seen[key] = r
    return list(seen.values())


def _extract_from_general_html(soup: BeautifulSoup) -> list[BankRate]:
    rates: list[BankRate] = []
    text = soup.get_text(separator="\n", strip=True)
    lines = text.split("\n")

    bank_keywords = [
        "Альфа Банк", "Банк БелВЭБ", "Банк ВТБ", "Банк Дабрабыт",
        "Банк Решение", "Банк РРБ", "Белагропромбанк", "Беларусбанк",
        "Белгазпромбанк", "Белинвестбанк", "БНБ-Банк", "БСБ Банк",
        "МТБанк", "Нео Банк Азия", "Паритетбанк", "Приорбанк",
        "Сбер Банк", "СтатусБанк", "Технобанк", "ТК Банк", "Цептер Банк",
        "BNB-Bank", "INSNC", "BSB-Bank", "Zepter", "Moby", "Альфа",
    ]

    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        bank_name: str | None = None
        for kw in bank_keywords:
            if kw.lower() in line.lower():
                bank_name = line
                break

        if bank_name:
            numbers: list[float] = []
            scan_end = min(idx + 8, len(lines))
            for j in range(idx + 1, scan_end):
                val = _parse_rate_value(lines[j])
                if val is not None:
                    numbers.append(val)
                if len(numbers) >= 2:
                    break

            if numbers:
                rates.append(
                    BankRate(
                        bank=bank_name,
                        buy=numbers[0] if len(numbers) >= 1 else None,
                        sell=numbers[1] if len(numbers) >= 2 else None,
                    )
                )
            idx += 1
        else:
            idx += 1

    return rates


async def fetch_page(url: str | None = None) -> str:
    target_url = url or config.PARSER_URL
    session = await get_session()

    for attempt in range(3):
        try:
            async with session.get(target_url) as response:
                response.raise_for_status()
                return await response.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning("Попытка %d не удалась для %s: %s", attempt + 1, target_url, exc)
            if attempt == 2:
                raise
            await asyncio.sleep(2 * (attempt + 1))
    return ""


async def parse_bank_rates(url: str | None = None) -> list[BankRate]:
    try:
        html = await fetch_page(url)
    except Exception:
        logger.exception("Ошибка при загрузке страницы")
        return []
    if not html:
        logger.error("Пустой ответ от сервера")
        return []
    rates = extract_bank_rates_from_html(html)
    if not rates:
        logger.warning("Не удалось извлечь курсы из HTML")
    return rates