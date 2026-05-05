from __future__ import annotations

import logging
from dataclasses import dataclass

from services.parser import BankRate, parse_bank_rates

logger = logging.getLogger(__name__)

_MEDALS = ["🥇", "🥈", "🥉"]


@dataclass
class BestRate:
    bank: str
    rate: float
    address: str | None = None
    branch_count: int = 1
    is_mobile: bool = False


async def get_best_rate(url: str | None = None) -> BestRate | None:
    rates = await parse_bank_rates(url)
    if not rates:
        logger.error("Нет данных о курсах")
        return None

    best: BankRate | None = None
    best_value: float = float("inf")
    for r in rates:
        if r.sell is not None and r.sell < best_value:
            best = r
            best_value = r.sell

    if best is None or best.sell is None:
        logger.error("Не найден курс продажи")
        return None

    return BestRate(
        bank=best.bank,
        rate=best.sell,
        address=best.address,
        branch_count=best.branch_count,
        is_mobile=best.is_mobile,
    )


_PER_PAGE = 8


def paginate(items: list, page: int, per_page: int = _PER_PAGE) -> tuple[list, int]:
    """Return slice for the given page and total number of pages."""
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], total_pages


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_address_line(rate: BankRate | BestRate) -> str | None:
    """Return a location line for a rate, or None if no location info."""
    if getattr(rate, "is_mobile", False):
        return None
    if rate.address:
        return f"📍 {_esc(rate.address)}"
    if rate.branch_count > 1:
        return f"📍 г. Гомель, {rate.branch_count} отделений"
    return None


def format_settings_text(user: dict, last_rate: dict | None, interval: int) -> str:
    """Return unified settings text."""
    status = "✅ Активны" if user["is_active"] else "❌ Выключены"
    threshold = f"<b>{user['threshold']}</b>" if user["threshold"] else "не установлен"
    last_info = "Нет данных"
    if last_rate:
        last_info = f"{last_rate['bank']}: <code>{last_rate['rate']}</code>"
    return (
        f"⚙️ <b>Настройки</b>\n\n"
        f"Уведомления: {status}\n"
        f"Порог: {threshold}\n"
        f"Последний курс: {last_info}\n"
        f"Проверка: каждые {interval} мин."
    )


def format_rate_info(result: BestRate) -> str:
    lines = [
        f"🏦 <b>Лучший курс покупки USD</b>\n"
        f"{_esc(result.bank)} — <code>{result.rate}</code> RUB/USD"
    ]
    addr = _format_address_line(result)
    if addr:
        lines.append(addr)
    return "\n".join(lines)


def format_all_rates(rates: list[BankRate], page: int = 1) -> str:
    if not rates:
        return "Нет данных о курсах."

    valid = sorted([r for r in rates if r.sell is not None], key=lambda r: r.sell)

    if not valid:
        return "Нет данных о курсах."

    page_items, total_pages = paginate(valid, page, _PER_PAGE)

    lines = [f"💱 <b>USD/RUB · Гомель</b>  <i>(стр. {page}/{total_pages})</i>\n"]

    global_pos = (page - 1) * _PER_PAGE + 1
    for r in page_items:
        sell_str = f"<code>{r.sell}</code>"

        if global_pos <= 3:
            medal = _MEDALS[global_pos - 1]
            if r.is_mobile:
                medal += "📱"
            lines.append(f"{medal} <b>{_esc(r.bank)}</b> — {sell_str} ₽")
            addr = _format_address_line(r)
            if addr:
                lines.append(f"   {addr}")
        else:
            medal = f"{global_pos}."
            buy_str = f"{r.buy}" if r.buy is not None else "—"
            lines.append(f"{medal} {_esc(r.bank)} · {sell_str} ₽ (сдача: {buy_str})")
        global_pos += 1

    best = valid[0]
    lines.append(f"\n────────────────")
    lines.append(f"🏆 Лучшая покупка: <b>{_esc(best.bank)}</b> за <code>{best.sell}</code> RUB")

    return "\n".join(lines)


def format_top_rates(rates: list[BankRate], n: int = 3) -> str:
    if not rates:
        return "Нет данных о курсах."

    valid = sorted([r for r in rates if r.sell is not None], key=lambda r: r.sell)
    if not valid:
        return "Нет данных о курсах."

    top = valid[:n]
    lines = [f"🏆 <b>Топ-{n} лучших курса · Гомель</b>\n"]

    for i, r in enumerate(top):
        medal = _MEDALS[i] if i < 3 else f"{i + 1}."
        if r.is_mobile:
            medal += "📱"
        lines.append(f"{medal} <b>{_esc(r.bank)}</b> — <code>{r.sell}</code> ₽")
        addr = _format_address_line(r)
        if addr:
            lines.append(f"   {addr}")

    return "\n".join(lines)


def format_history(history: list[dict], page: int = 1) -> str:
    if not history:
        return "Пока нет данных."

    page_items, total_pages = paginate(history, page, _PER_PAGE)

    lines = [f"📜 <b>История USD/RUB · Гомель</b>  <i>(стр. {page}/{total_pages})</i>\n"]

    for i, entry in enumerate(page_items):
        rate = entry["rate"]
        bank = entry["bank"]
        checked_at = entry.get("checked_at", "")

        if " " in checked_at:
            date_part, time_part = checked_at.split(" ", 1)
            dt_display = f"{date_part[5:]} {time_part[:5]}"
        else:
            dt_display = checked_at

        # Compare with next entry in the FULL list (not page)
        full_idx = (page - 1) * _PER_PAGE + i
        if full_idx < len(history) - 1:
            prev_rate = history[full_idx + 1]["rate"]
            diff = round(rate - prev_rate, 4)
            if diff > 0:
                arrow = f" ↑+{diff}"
            elif diff < 0:
                arrow = f" ↓{diff}"
            else:
                arrow = " →"
        else:
            arrow = ""

        lines.append(f"<code>{rate}</code> {_esc(bank)} · {dt_display}{arrow}")

    return "\n".join(lines)
