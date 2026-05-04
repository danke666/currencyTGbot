import asyncio
import logging

from aiogram import Bot

import config
import database.db as db
from services.rate_service import BestRate, format_rate_info, parse_bank_rates

logger = logging.getLogger(__name__)


async def _send_to_all(bot: Bot, user_ids: list[int], text: str) -> None:
    for uid in user_ids:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
        except Exception:
            logger.exception("Не удалось отправить уведомление user_id=%s", uid)


async def run_notifier(bot: Bot) -> None:
    interval = config.CHECK_INTERVAL_MINUTES * 60
    logger.info("Notifier запущен (интервал: %d мин.)", config.CHECK_INTERVAL_MINUTES)

    while True:
        await asyncio.sleep(interval)
        try:
            rates = await parse_bank_rates(config.PARSER_URL)
            if not rates:
                logger.warning("Не удалось получить курс для уведомлений")
                continue

            valid = [r for r in rates if r.sell is not None]
            if not valid:
                logger.warning("Нет валидных курсов")
                continue

            best = min(valid, key=lambda r: r.sell)
            result = BestRate(bank=best.bank, rate=best.sell)

            last = await db.get_last_rate()
            await db.save_rate(result.bank, result.rate)

            users = await db.get_active_users()
            if not users:
                continue

            rate_changed = (
                last is None
                or last["bank"] != result.bank
                or last["rate"] != result.rate
            )

            if not rate_changed:
                continue

            base_text = f"🔄 <b>Курс USD/RUB изменился</b>\n\n{format_rate_info(result)}"

            if last is not None and result.rate < last["rate"]:
                diff = round(last["rate"] - result.rate, 4)
                base_text += f"\n\n📉 Снижение на {diff} RUB — выгоднее покупать!"
            elif last is not None and result.rate > last["rate"]:
                diff = round(result.rate - last["rate"], 4)
                base_text += f"\n\n📈 Рост на {diff} RUB"

            threshold_user_ids: set[int] = set()
            for user in users:
                threshold = user["threshold"]
                if threshold and result.rate <= threshold:
                    threshold_user_ids.add(user["user_id"])
                    try:
                        await bot.send_message(
                            user["user_id"],
                            base_text + f"\n\n⚡ Курс ниже вашего порога: {threshold}",
                            parse_mode="HTML",
                        )
                    except Exception:
                        logger.exception("Не удалось отправить user_id=%s", user["user_id"])

            other_ids = [u["user_id"] for u in users if u["user_id"] not in threshold_user_ids]
            if other_ids:
                await _send_to_all(bot, other_ids, base_text)

        except Exception:
            logger.exception("Ошибка в цикле уведомлений")