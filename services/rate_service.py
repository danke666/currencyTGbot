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

    return BestRate(bank=best.bank, rate=best.sell)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_rate_info(result: BestRate) -> str:
    return (
        f"🏦 <b>Лучший курс покупки USD</b>\n"
        f"{_esc(result.bank)} — <code>{result.rate}</code> RUB/USD"
    )


def format_all_rates(rates: list[BankRate]) -> str:
    if not rates:
        return "Нет данных о курсах."

    valid = [(i, r) for i, r in enumerate(sorted(rates, key=lambda r: r.sell or float("inf")))
             if r.sell is not None]

    if not valid:
        return "Нет данных о курсах."

    lines = ["💱 <b>USD/RUB · Гомель</b>\n"]

    for pos, (_, r) in enumerate(valid, 1):
        medal = _MEDALS[pos - 1] if pos <= 3 else f"{pos}."
        sell_str = f"<code>{r.sell}</code>"

        if pos <= 3:
            lines.append(f"{medal} <b>{_esc(r.bank)}</b> — {sell_str} ₽")
        else:
            buy_str = f"{r.buy}" if r.buy is not None else "—"
            lines.append(f"{medal} {_esc(r.bank)} · {sell_str} ₽ (сдача: {buy_str})")

    best = valid[0][1]
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
        lines.append(f"{medal} <b>{_esc(r.bank)}</b> — <code>{r.sell}</code> ₽")

    return "\n".join(lines)


def format_history(history: list[dict]) -> str:
    if not history:
        return "Пока нет данных."

    lines = ["📜 <b>История USD/RUB · Гомель</b>\n"]

    for i, entry in enumerate(history):
        rate = entry["rate"]
        bank = entry["bank"]
        checked_at = entry.get("checked_at", "")

        if " " in checked_at:
            date_part, time_part = checked_at.split(" ", 1)
            dt_display = f"{date_part[5:]} {time_part[:5]}"
        else:
            dt_display = checked_at

        if i < len(history) - 1:
            prev_rate = history[i + 1]["rate"]
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