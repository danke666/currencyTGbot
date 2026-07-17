import asyncio
import logging

from aiogram import Bot

import config
import database.db as db
from services.rate_service import BestRate, format_rate_info, parse_bank_rates

logger = logging.getLogger(__name__)

_stop_event = asyncio.Event()
_send_sem = asyncio.Semaphore(5)


async def _send_one(bot: Bot, user_id: int, text: str) -> None:
    if _stop_event.is_set():
        return
    try:
        async with _send_sem:
            await bot.send_message(user_id, text, parse_mode="HTML")
    except Exception:
        logger.exception("Не удалось отправить уведомление user_id=%s", user_id)


async def _send_to_all(bot: Bot, user_ids: list[int], text: str) -> None:
    if not user_ids or _stop_event.is_set():
        return
    tasks = [_send_one(bot, uid, text) for uid in user_ids]
    await asyncio.gather(*tasks, return_exceptions=True)


def stop_notifier() -> None:
    _stop_event.set()


async def run_notifier(bot: Bot) -> None:
    interval = config.CHECK_INTERVAL_MINUTES * 60
    logger.info("Notifier запущен (интервал: %d мин.)", config.CHECK_INTERVAL_MINUTES)

    while not _stop_event.is_set():
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            break

        if _stop_event.is_set():
            break

        for city, url in config.CITY_URLS.items():
            try:
                await _check_city(bot, city, url)
            except Exception:
                logger.exception("Ошибка проверки курсов для города %s", city)


async def _check_city(bot: Bot, city: str, url: str) -> None:
    rates = await parse_bank_rates(url)
    if not rates:
        logger.warning("Не удалось получить курс для %s", city)
        return

    valid = [r for r in rates if r.sell is not None]
    if not valid:
        logger.warning("Нет валидных курсов для %s", city)
        return

    best = min(valid, key=lambda r: r.sell)
    result = BestRate(
        bank=best.bank, rate=best.sell, address=best.address,
        branch_count=best.branch_count, is_mobile=best.is_mobile,
    )

    last = await db.get_last_rate(city)
    await db.save_rate(result.bank, result.rate, city)
    await db.cleanup_rate_history()

    users = [u for u in await db.get_active_users() if u["city"] == city]
    if not users:
        return

    rate_changed = last is None or last["bank"] != result.bank or last["rate"] != result.rate
    if not rate_changed:
        return

    city_name = config.CITY_NAMES[city]
    base_text = (
        f"🔄 <b>Курс USD/RUB изменился · {city_name}</b>\n\n"
        f"{format_rate_info(result, city)}"
    )

    if last is not None and result.rate < last["rate"]:
        diff = round(last["rate"] - result.rate, 4)
        base_text += f"\n\n📉 Снижение на {diff} RUB — выгоднее покупать!"
    elif last is not None and result.rate > last["rate"]:
        diff = round(result.rate - last["rate"], 4)
        base_text += f"\n\n📈 Рост на {diff} RUB"

    threshold_tasks = []
    threshold_user_ids: set[int] = set()
    for user in users:
        threshold = user["threshold"]
        if threshold and result.rate <= threshold:
            threshold_user_ids.add(user["user_id"])
            text = base_text + f"\n\n⚡ Курс ниже вашего порога: {threshold}"
            threshold_tasks.append(_send_one(bot, user["user_id"], text))

    if threshold_tasks:
        await asyncio.gather(*threshold_tasks, return_exceptions=True)

    other_ids = [u["user_id"] for u in users if u["user_id"] not in threshold_user_ids]
    if other_ids:
        await _send_to_all(bot, other_ids, base_text)
