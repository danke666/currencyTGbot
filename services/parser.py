import asyncio
import logging
import re
import time
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
_http_sem = asyncio.Semaphore(2)


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
    address: str | None = None
    branch_count: int = 1
    is_mobile: bool = False


# In-memory TTL cache is keyed by URL so different cities never share data.
_cache: dict[str, tuple[float, list[BankRate]]] = {}
CACHE_TTL: float = 90.0


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


_MOBILE_KEYWORDS = ["app", "mobile", "insnc", "moby", "приложение"]


def _is_mobile_app(name: str) -> bool:
    """Detect mobile-app / online-only entries by name."""
    lower = name.lower()
    return any(kw in lower for kw in _MOBILE_KEYWORDS)


def _extract_bank_name_from_row(bank_row) -> str | None:
    """Extract clean bank name from a main table row."""
    name_cell = bank_row.find("td")
    if not name_cell:
        return None

    # Prefer img alt attribute (cleanest name)
    img = name_cell.find("img")
    if img and img.get("alt"):
        return img.get("alt").strip()

    # Fallback to text content, stripping extra whitespace
    text = name_cell.get_text(separator=" ", strip=True)
    # Remove any trailing numeric badges like " 5 " or " 34 "
    text = re.sub(r"\s+\d+\s*$", "", text).strip()
    return text if text else None


def _extract_branch_data(branch_container) -> list[dict]:
    """Extract branch rates from the nested branch table."""
    branches: list[dict] = []
    branch_table = branch_container.select_one("table.currencies-courses--branches")
    if not branch_table:
        return branches

    for branch_tr in branch_table.select("tbody tr"):
        # Skip promo/appointment rows
        if "currencies-courses__appointment-row" in branch_tr.get("class", []):
            continue

        addr_a = branch_tr.select_one("a.currencies-courses__branch-name")
        address = addr_a.get_text(strip=True) if addr_a else None

        rate_cells = branch_tr.select("td.currencies-courses__currency-cell span")
        buy = _parse_rate_value(rate_cells[0].get_text(strip=True)) if len(rate_cells) > 0 else None
        sell = _parse_rate_value(rate_cells[1].get_text(strip=True)) if len(rate_cells) > 1 else None

        if sell is not None:
            branches.append({"address": address, "buy": buy, "sell": sell})

    return branches


def _build_rate_from_main_row(bank_row) -> BankRate | None:
    """Fallback: build BankRate from main row when branches are unavailable."""
    bank_name = _extract_bank_name_from_row(bank_row)
    if not bank_name:
        return None

    rate_cells = bank_row.select("td.currencies-courses__currency-cell span")
    buy = _parse_rate_value(rate_cells[0].get_text(strip=True)) if len(rate_cells) > 0 else None
    sell = _parse_rate_value(rate_cells[1].get_text(strip=True)) if len(rate_cells) > 1 else None

    if sell is None:
        return None

    return BankRate(bank=bank_name, buy=buy, sell=sell, address=None, branch_count=1)


def extract_bank_rates_from_html(html: str) -> list[BankRate]:
    soup = BeautifulSoup(html, "lxml")
    rates: list[BankRate] = []

    # ── Strategy 1: structured table with nested branch tables ──
    outer_table = soup.find("table", class_="currencies-courses")
    if outer_table:
        for bank_row in outer_table.find_all("tr", class_="currencies-courses__row-main"):
            is_ad = "currencies-courses__row-main--ad" in bank_row.get("class", [])
            bank_name = _extract_bank_name_from_row(bank_row)
            if not bank_name:
                continue

            # Pure promo banners (e.g. "Забронировать курс") — skip
            if is_ad and not _is_mobile_app(bank_name):
                continue

            # Extract bank-wide rates from main row
            main_rate_cells = bank_row.select("td.currencies-courses__currency-cell span")
            bank_buy = _parse_rate_value(main_rate_cells[0].get_text(strip=True)) if len(main_rate_cells) > 0 else None
            bank_sell = _parse_rate_value(main_rate_cells[1].get_text(strip=True)) if len(main_rate_cells) > 1 else None

            # Mobile / online-only app entry — no physical branches
            if is_ad and _is_mobile_app(bank_name):
                if bank_sell is not None:
                    rates.append(
                        BankRate(
                            bank=bank_name,
                            buy=bank_buy,
                            sell=bank_sell,
                            address=None,
                            branch_count=0,
                            is_mobile=True,
                        )
                    )
                continue

            # Look for the branch container in the next sibling row
            branch_container = bank_row.find_next_sibling("tr", class_="currencies-courses__row-additional")
            if branch_container:
                branches = _extract_branch_data(branch_container)
                if branches:
                    best = min(branches, key=lambda b: b["sell"])
                    min_sell = best["sell"]
                    all_same = all(b["sell"] == min_sell for b in branches)

                    if all_same:
                        rates.append(
                            BankRate(
                                bank=bank_name,
                                buy=bank_buy,
                                sell=min_sell,
                                address=None,
                                branch_count=len(branches),
                                is_mobile=False,
                            )
                        )
                    else:
                        rates.append(
                            BankRate(
                                bank=bank_name,
                                buy=best["buy"],
                                sell=min_sell,
                                address=best["address"],
                                branch_count=1,
                                is_mobile=False,
                            )
                        )
                    continue  # branches parsed successfully

            # Fallback to main-row rate if no branches found
            if bank_sell is not None:
                rates.append(
                    BankRate(
                        bank=bank_name,
                        buy=bank_buy,
                        sell=bank_sell,
                        address=None,
                        branch_count=1,
                        is_mobile=False,
                    )
                )

    if rates:
        return _deduplicate(rates)

    # ── Strategy 2: old div-based layout (legacy fallback) ──
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

        rates.append(
            BankRate(
                bank=bank_name,
                buy=buy_rate,
                sell=sell_rate,
                is_mobile=False,
            )
        )

    if rates:
        return _deduplicate(rates)

    # ── Strategy 3: plain-text extraction (last resort) ──
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

    bank_keywords = [
        "Альфа Банк", "Банк БелВЭБ", "Банк ВТБ", "Банк Дабрабыт",
        "Банк Решение", "Банк РРБ", "Белагропромбанк", "Беларусбанк",
        "Белгазпромбанк", "Белинвестбанк", "БНБ-Банк", "БСБ Банк",
        "МТБанк", "Нео Банк Азия", "Паритетбанк", "Приорбанк",
        "Сбер Банк", "СтатусБанк", "Технобанк", "ТК Банк", "Цептер Банк",
        "BNB-Bank", "INSNC", "BSB-Bank", "Zepter", "Moby", "Альфа",
    ]

    keyword_pattern = re.compile(
        "(" + "|".join(re.escape(kw) for kw in bank_keywords) + ")",
        re.IGNORECASE,
    )

    lines = text.split("\n")
    for match in keyword_pattern.finditer(text):
        line_start = text[:match.start()].count("\n")
        bank_name = lines[line_start]

        numbers: list[float] = []
        scan_end = min(line_start + 9, len(lines))
        for j in range(line_start + 1, scan_end):
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
                    is_mobile=False,
                )
            )

    return rates


async def fetch_page(url: str | None = None) -> str:
    target_url = url or config.PARSER_URL
    session = await get_session()

    for attempt in range(3):
        try:
            async with _http_sem:
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
    target_url = url or config.PARSER_URL
    now = time.monotonic()
    cached = _cache.get(target_url)

    if cached is not None and (now - cached[0]) < CACHE_TTL:
        logger.debug("Returning cached rates for %s (age=%.1fs)", target_url, now - cached[0])
        return list(cached[1])

    html = ""
    try:
        html = await fetch_page(target_url)
    except Exception:
        logger.exception("Ошибка при загрузке страницы")
    if not html:
        logger.error("Пустой ответ от сервера")
        # Fallback to stale cache (up to 5 min old) on fetch error
        if cached is not None and (now - cached[0]) < 300:
            logger.warning("Returning stale cache for %s due to fetch error", target_url)
            return list(cached[1])
        return []

    loop = asyncio.get_running_loop()
    rates: list[BankRate] = []
    try:
        rates = await loop.run_in_executor(None, extract_bank_rates_from_html, html)
    except Exception:
        logger.exception("Ошибка при парсинге HTML")

    if not rates:
        logger.warning("Не удалось извлечь курсы из HTML")
        # Fallback to stale cache on parse error
        if cached is not None and (now - cached[0]) < 300:
            logger.warning("Returning stale cache for %s due to parse error", target_url)
            return list(cached[1])

    if rates:
        _cache[target_url] = (now, list(rates))

    return rates
