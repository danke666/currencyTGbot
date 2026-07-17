import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, BotCommandScopeDefault

import config
import database.db as db
from bot.handlers import router
from bot.notifier import run_notifier, stop_notifier
from services.parser import close_session
from utils.logger import setup_logging

logger = logging.getLogger(__name__)

_COMMANDS = [
    BotCommand(command="start", description="🏠 Меню бота"),
    BotCommand(command="menu", description="🏠 Меню бота"),
    BotCommand(command="rate", description="💼 Все курсы банков"),
    BotCommand(command="set_threshold", description="⚡ Порог уведомления"),
    BotCommand(command="off_threshold", description="❌ Сбросить порог"),
    BotCommand(command="notify", description="🔔 Вкл/выкл уведомления"),
    BotCommand(command="calc", description="🧮 Рассчитать обмен"),
]


async def main() -> None:
    setup_logging(config.LOG_LEVEL)
    logger.info("Запуск бота...")

    if not config.BOT_TOKEN:
        logger.critical("BOT_TOKEN не задан! Установите .env файл.")
        return

    await db.init_db()
    logger.info("База данных инициализирована")

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_my_commands(scope=BotCommandScopeDefault())

    notifier_task = asyncio.create_task(run_notifier(bot))

    try:
        logger.info("Бот запущен. Для остановки нажмите Ctrl+C.")
        await dp.start_polling(bot)
    finally:
        logger.info("Остановка бота...")
        stop_notifier()
        notifier_task.cancel()
        try:
            await notifier_task
        except asyncio.CancelledError:
            pass
        await close_session()
        await db.close_db()
        await bot.session.close()
        logger.info("Бот остановлен.")
