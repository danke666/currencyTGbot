"""Native Telegram Rich Message helpers with a safe HTML fallback path."""

from __future__ import annotations

import html
import logging

import aiohttp
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

import config
from services.parser import BankRate

logger = logging.getLogger(__name__)


def build_rates_rich_html(rates: list[BankRate], city: str) -> str:
    """Build a structured native Rich Message for the first rate page."""
    valid = sorted((rate for rate in rates if rate.sell is not None), key=lambda rate: rate.sell)[:8]
    rows = "".join(
        "<tr>"
        f"<td>{index}. {html.escape(rate.bank)}</td>"
        f"<td><strong>{rate.sell} RUB</strong></td>"
        "</tr>"
        for index, rate in enumerate(valid, start=1)
    )
    best = valid[0] if valid else None
    best_text = (
        f"Лучший курс: <strong>{html.escape(best.bank)} — {best.sell} RUB/USD</strong>"
        if best else "Курсы временно недоступны"
    )
    return (
        f"<h2>💱 USD/RUB · {html.escape(config.CITY_NAMES[city])}</h2>"
        "<p>Курс продажи USD — сколько нужно заплатить банку за 1 доллар.</p>"
        "<table><thead><tr><th>Банк</th><th>Курс</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        f"<p>{best_text}</p>"
        "<footer>Источник: <a href=\"https://myfin.by/\">Myfin.by</a>. "
        "Проверьте наличие валюты в отделении перед обменом.</footer>"
    )


async def send_rates_rich_message(
    bot: Bot,
    chat_id: int,
    rates: list[BankRate],
    city: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    """Send a Bot API 10.1+ Rich Message; return False if unavailable."""
    payload: dict = {
        "chat_id": chat_id,
        "rich_message": {"html": build_rates_rich_html(rates, city)},
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup.model_dump(by_alias=True, exclude_none=True)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.telegram.org/bot{bot.token}/sendRichMessage",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                result = await response.json(content_type=None)
        if result.get("ok"):
            return True
        logger.info("Rich Message unavailable, using HTML fallback: %s", result.get("description"))
    except (aiohttp.ClientError, ValueError):
        logger.info("Could not send Rich Message; using HTML fallback", exc_info=True)
    return False
