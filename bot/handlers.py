import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery

import config
import database.db as db
from services.rate_service import (
    format_rate_info,
    format_all_rates,
    format_top_rates,
    format_history,
)
from services.parser import parse_bank_rates
from bot.callbacks import ActionCallback
from bot.keyboards import rate_actions_keyboard

logger = logging.getLogger(__name__)

router = Router()

_START_TEXT = (
    "👋 <b>Добро пожаловать!</b>\n"
    "Бот отслеживает лучший курс покупки USD за RUB в Гомеле.\n\n"
    "📊 <b>Курсы:</b>\n"
    "/rate — все банки\n"
    "/top — топ-3 лучших\n\n"
    "🔔 <b>Уведомления:</b>\n"
    "/notify — вкл/выкл\n"
    "/set_threshold — порог (при курсе ≤ порога)\n\n"
    "⚙️ <b>Другое:</b>\n"
    "/history — история изменений\n"
    "/status — ваши настройки"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id
    existing = await db.get_user(user_id)
    if existing:
        await message.answer(_START_TEXT, parse_mode="HTML")
        return
    await db.add_user(user_id)
    await message.answer(_START_TEXT, parse_mode="HTML")


@router.message(Command("rate"))
async def cmd_rate(message: Message) -> None:
    wait_msg = await message.answer("⏳ Получаю курсы...")
    try:
        rates = await parse_bank_rates(config.PARSER_URL)
        if not rates:
            await wait_msg.edit_text("Не удалось получить курсы. Попробуйте позже.")
            return
        text = format_all_rates(rates)
        await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=rate_actions_keyboard())
    except Exception:
        logger.exception("Ошибка при получении курсов")
        await wait_msg.edit_text("Произошла ошибка. Попробуйте позже.")


@router.message(Command("top"))
async def cmd_top(message: Message) -> None:
    wait_msg = await message.answer("⏳ Получаю курсы...")
    try:
        rates = await parse_bank_rates(config.PARSER_URL)
        if not rates:
            await wait_msg.edit_text("Не удалось получить курсы. Попробуйте позже.")
            return
        text = format_top_rates(rates)
        await wait_msg.edit_text(text, parse_mode="HTML")
    except Exception:
        logger.exception("Ошибка при получении курсов")
        await wait_msg.edit_text("Произошла ошибка. Попробуйте позже.")


@router.message(Command("history"))
async def cmd_history(message: Message) -> None:
    history = await db.get_rate_history(limit=10)
    if not history:
        await message.answer("Пока нет данных. Курсы появятся после первой проверки.")
        return
    text = format_history(history)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("set_threshold"))
async def cmd_set_threshold(message: Message) -> None:
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer(
            "💡 Установите порог — бот уведомит, когда курс ≤ порога.\n\n"
            "Пример:\n/set_threshold 76.5"
        )
        return

    try:
        threshold = float(args[1].replace(",", "."))
    except ValueError:
        await message.answer("Введите корректное число.\nПример: /set_threshold 76.5")
        return

    existing = await db.get_user(user_id)
    if not existing:
        await db.add_user(user_id)

    await db.set_threshold(user_id, threshold)
    await message.answer(
        f"✅ Порог: <b>{threshold}</b> RUB/USD\n"
        f"Уведомлю, когда курс ≤ {threshold}",
        parse_mode="HTML",
    )


@router.message(Command("notify"))
async def cmd_notify(message: Message) -> None:
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not user:
        await db.add_user(user_id)
        user = await db.get_user(user_id)
        if not user:
            await message.answer("Ошибка. Попробуйте /start.")
            return

    new_active = not user["is_active"]
    await db.toggle_user_active(user_id, new_active)

    if new_active:
        await message.answer("🔔 Уведомления <b>включены</b>.", parse_mode="HTML")
    else:
        await message.answer("🔕 Уведомления <b>выключены</b>.", parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    user_id = message.from_user.id
    user = await db.get_user(user_id)

    if not user:
        await message.answer("Вы не зарегистрированы. Нажмите /start")
        return

    last_rate = await db.get_last_rate()
    last_info = "Нет данных"
    if last_rate:
        last_info = f"{last_rate['bank']}: <code>{last_rate['rate']}</code>"

    status = "✅ Активны" if user["is_active"] else "❌ Выключены"
    threshold = f"<b>{user['threshold']}</b>" if user["threshold"] else "не установлен"

    await message.answer(
        f"⚙️ <b>Ваши настройки</b>\n\n"
        f"Уведомления: {status}\n"
        f"Порог: {threshold}\n"
        f"Последний курс: {last_info}\n"
        f"Проверка: каждые {config.CHECK_INTERVAL_MINUTES} мин.",
        parse_mode="HTML",
    )


@router.message(F.text.lower().in_({"привет", "hello", "hi"}))
async def cmd_hello(message: Message) -> None:
    await message.answer(
        "Привет! Я бот курсов USD/RUB в Гомеле.\n"
        "Нажми /rate чтобы узнать текущий курс."
    )


@router.callback_query(ActionCallback.filter())
async def process_action_callback(callback: CallbackQuery, callback_data: ActionCallback) -> None:
    action = callback_data.action

    if action == "top":
        rates = await parse_bank_rates(config.PARSER_URL)
        if not rates:
            await callback.message.edit_text("Не удалось получить курсы.")
            await callback.answer()
            return
        text = format_top_rates(rates)
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=rate_actions_keyboard())
        await callback.answer()

    elif action == "history":
        history = await db.get_rate_history(limit=10)
        if not history:
            await callback.answer("Пока нет данных по истории", show_alert=True)
            return
        text = format_history(history)
        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.answer()

    else:
        await callback.answer()