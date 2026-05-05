import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

import config
import database.db as db
from services.rate_service import (
    format_all_rates,
    format_top_rates,
    format_history,
    format_settings_text,
    paginate,
)
from services.parser import parse_bank_rates
from bot.callbacks import MenuCallback, PageCallback, SettingsCallback
from bot.keyboards import (
    main_reply_keyboard,
    pagination_keyboard,
    rate_keyboard,
    top_keyboard,
    history_keyboard,
    settings_keyboard,
)

logger = logging.getLogger(__name__)

router = Router()

_WELCOME_TEXT = (
    "👋 <b>Курс USD/RUB · Гомель</b>\n\n"
    "Бот находит лучший курс покупки долларов за рубли "
    "и уведомляет при изменениях.\n\n"
    "Нажмите кнопку ниже или используйте команды 👇"
)




async def _safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest as exc:
        # Expected errors: message already deleted, no permission
        if "message to delete not found" not in str(exc).lower() and "message can't be deleted" not in str(exc).lower():
            logger.warning("Unexpected delete error: %s", exc)
    except Exception:
        logger.debug("Delete error", exc_info=True)


async def _safe_edit_text(message: Message, text: str, reply_markup=None) -> bool:
    """Edit message text, return True on success. Log unexpected errors."""
    try:
        await message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
        return True
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return True  # Not an error
        logger.warning("Edit text error: %s", exc)
        return False
    except Exception:
        logger.exception("Unexpected edit text error")
        return False


async def _ensure_user(user_id: int) -> dict:
    user = await db.get_user(user_id)
    if not user:
        await db.add_user(user_id)
        user = await db.get_user(user_id)
    return user


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await _ensure_user(message.from_user.id)
    await message.answer(
        _WELCOME_TEXT,
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(),
    )
    await _safe_delete(message)


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer(_WELCOME_TEXT, parse_mode="HTML", reply_markup=main_reply_keyboard())
    await _safe_delete(message)


@router.message(F.text == "📊 Курсы")
async def btn_rates(message: Message) -> None:
    wait_msg = await message.answer("⏳ Получаю курсы...")
    try:
        rates = await parse_bank_rates(config.PARSER_URL)
        if not rates:
            await wait_msg.edit_text("Не удалось получить курсы. Попробуйте позже.")
            return
        _, total_pages = paginate([r for r in rates if r.sell is not None], 1)
        text = format_all_rates(rates, page=1)
        kb = rate_keyboard()
        if total_pages > 1:
            # Combine rate keyboard row with pagination
            kb.inline_keyboard.extend(
                pagination_keyboard("rate", 1, total_pages).inline_keyboard
            )
        await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        logger.exception("Ошибка при получении курсов")
        await wait_msg.edit_text("Произошла ошибка. Попробуйте позже.")
    finally:
        await _safe_delete(message)


@router.message(F.text == "🏆 Топ-3")
async def btn_top(message: Message) -> None:
    wait_msg = await message.answer("⏳ Получаю курсы...")
    try:
        rates = await parse_bank_rates(config.PARSER_URL)
        if not rates:
            await wait_msg.edit_text("Не удалось получить курсы. Попробуйте позже.")
            return
        text = format_top_rates(rates)
        await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=top_keyboard())
    except Exception:
        logger.exception("Ошибка при получении курсов")
        await wait_msg.edit_text("Произошла ошибка. Попробуйте позже.")
    finally:
        await _safe_delete(message)


@router.message(F.text == "📜 История")
async def btn_history(message: Message) -> None:
    history = await db.get_rate_history(limit=80)  # Fetch enough for pagination
    if not history:
        await message.answer("Пока нет данных. Курсы появятся после первой проверки.")
    else:
        _, total_pages = paginate(history, 1)
        text = format_history(history, page=1)
        kb = history_keyboard()
        if total_pages > 1:
            kb.inline_keyboard.extend(
                pagination_keyboard("history", 1, total_pages).inline_keyboard
            )
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
    await _safe_delete(message)


@router.message(F.text == "⚙️ Настройки")
async def btn_settings(message: Message) -> None:
    user_id = message.from_user.id
    await _ensure_user(user_id)
    user = await db.get_user(user_id)

    last_rate = await db.get_last_rate()
    text = format_settings_text(user, last_rate, config.CHECK_INTERVAL_MINUTES)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=settings_keyboard(bool(user["is_active"]), bool(user["threshold"])),
    )
    await _safe_delete(message)


@router.message(Command("rate"))
async def cmd_rate(message: Message) -> None:
    wait_msg = await message.answer("⏳ Получаю курсы...")
    try:
        rates = await parse_bank_rates(config.PARSER_URL)
        if not rates:
            await wait_msg.edit_text("Не удалось получить курсы. Попробуйте позже.")
            return
        _, total_pages = paginate([r for r in rates if r.sell is not None], 1)
        text = format_all_rates(rates, page=1)
        kb = rate_keyboard()
        if total_pages > 1:
            kb.inline_keyboard.extend(
                pagination_keyboard("rate", 1, total_pages).inline_keyboard
            )
        await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        logger.exception("Ошибка при получении курсов")
        await wait_msg.edit_text("Произошла ошибка. Попробуйте позже.")
    finally:
        await _safe_delete(message)


@router.message(Command("set_threshold"))
async def cmd_set_threshold(message: Message) -> None:
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer(
            "💡 Установите порог — бот уведомит, когда курс ≤ порога.\n\n"
            "Пример:\n/set_threshold 76.5"
        )
        await _safe_delete(message)
        return

    try:
        threshold = float(args[1].replace(",", "."))
    except ValueError:
        await message.answer("Введите корректное число.\nПример: /set_threshold 76.5")
        await _safe_delete(message)
        return

    await _ensure_user(user_id)
    await db.set_threshold(user_id, threshold)
    await message.answer(
        f"✅ Порог: <b>{threshold}</b> RUB/USD\n"
        f"Уведомлю, когда курс ≤ {threshold}",
        parse_mode="HTML",
    )
    await _safe_delete(message)


@router.message(Command("off_threshold"))
async def cmd_off_threshold(message: Message) -> None:
    user_id = message.from_user.id
    await _ensure_user(user_id)
    await db.clear_threshold(user_id)
    await message.answer("❌ Порог уведомления <b>сброшен</b>.", parse_mode="HTML")
    await _safe_delete(message)


@router.message(Command("notify"))
async def cmd_notify(message: Message) -> None:
    user_id = message.from_user.id
    user = await _ensure_user(user_id)

    new_active = not user["is_active"]
    await db.toggle_user_active(user_id, new_active)

    if new_active:
        await message.answer("🔔 Уведомления <b>включены</b>.", parse_mode="HTML")
    else:
        await message.answer("🔕 Уведомления <b>выключены</b>.", parse_mode="HTML")
    await _safe_delete(message)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    user_id = message.from_user.id
    await _ensure_user(user_id)
    user = await db.get_user(user_id)

    last_rate = await db.get_last_rate()
    text = format_settings_text(user, last_rate, config.CHECK_INTERVAL_MINUTES)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=settings_keyboard(bool(user["is_active"]), bool(user["threshold"])),
    )
    await _safe_delete(message)


@router.message(F.text.lower().in_({"привет", "hello", "hi"}))
async def cmd_hello(message: Message) -> None:
    await _ensure_user(message.from_user.id)
    await message.answer(
        _WELCOME_TEXT,
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(),
    )
    await _safe_delete(message)


# ─── Inline: Main menu callbacks ─────────────────────────────────

@router.callback_query(MenuCallback.filter())
async def process_menu_callback(callback: CallbackQuery, callback_data: MenuCallback) -> None:
    action = callback_data.action
    user_id = callback.from_user.id
    await _ensure_user(user_id)

    if action == "rate":
        try:
            rates = await parse_bank_rates(config.PARSER_URL)
        except Exception:
            logger.exception("Ошибка при получении курсов в callback")
            await callback.answer("❌ Не удалось загрузить данные", show_alert=True)
            return
        if not rates:
            await callback.answer("Не удалось получить курсы", show_alert=True)
            return
        _, total_pages = paginate([r for r in rates if r.sell is not None], 1)
        text = format_all_rates(rates, page=1)
        kb = rate_keyboard()
        if total_pages > 1:
            kb.inline_keyboard.extend(
                pagination_keyboard("rate", 1, total_pages).inline_keyboard
            )
        await _safe_edit_text(callback.message, text, kb)
        await callback.answer()

    elif action == "top":
        try:
            rates = await parse_bank_rates(config.PARSER_URL)
        except Exception:
            logger.exception("Ошибка при получении курсов в callback")
            await callback.answer("❌ Не удалось загрузить данные", show_alert=True)
            return
        if not rates:
            await callback.answer("Не удалось получить курсы", show_alert=True)
            return
        text = format_top_rates(rates)
        await _safe_edit_text(callback.message, text, top_keyboard())
        await callback.answer()

    elif action == "history":
        history = await db.get_rate_history(limit=80)
        if not history:
            await callback.answer("Пока нет данных", show_alert=True)
            return
        _, total_pages = paginate(history, 1)
        text = format_history(history, page=1)
        kb = history_keyboard()
        if total_pages > 1:
            kb.inline_keyboard.extend(
                pagination_keyboard("history", 1, total_pages).inline_keyboard
            )
        await _safe_edit_text(callback.message, text, kb)
        await callback.answer()

    elif action == "settings":
        user = await db.get_user(user_id)
        if not user:
            await callback.answer("Нажмите /start", show_alert=True)
            return

        last_rate = await db.get_last_rate()
        text = format_settings_text(user, last_rate, config.CHECK_INTERVAL_MINUTES)
        kb = settings_keyboard(bool(user["is_active"]), bool(user["threshold"]))
    await _safe_edit_text(callback.message, text, kb)
    await callback.answer()


# ─── Inline: Pagination callbacks ─────────────────────────────────

@router.callback_query(PageCallback.filter())
async def process_page_callback(callback: CallbackQuery, callback_data: PageCallback) -> None:
    action = callback_data.action
    page = callback_data.page

    if action == "rate":
        try:
            rates = await parse_bank_rates(config.PARSER_URL)
        except Exception:
            logger.exception("Ошибка при получении курсов в callback")
            await callback.answer("❌ Не удалось загрузить данные", show_alert=True)
            return
        if not rates:
            await callback.answer("Не удалось получить курсы", show_alert=True)
            return
        valid = [r for r in rates if r.sell is not None]
        _, total_pages = paginate(valid, page)
        text = format_all_rates(rates, page=page)
        kb = rate_keyboard()
        if total_pages > 1:
            kb.inline_keyboard.extend(
                pagination_keyboard("rate", page, total_pages).inline_keyboard
            )
        await _safe_edit_text(callback.message, text, kb)
        await callback.answer()

    elif action == "history":
        history = await db.get_rate_history(limit=80)
        if not history:
            await callback.answer("Пока нет данных", show_alert=True)
            return
        _, total_pages = paginate(history, page)
        text = format_history(history, page=page)
        kb = history_keyboard()
        if total_pages > 1:
            kb.inline_keyboard.extend(
                pagination_keyboard("history", page, total_pages).inline_keyboard
            )
        await _safe_edit_text(callback.message, text, kb)
        await callback.answer()


# ─── Inline: Settings callbacks ──────────────────────────────────

@router.callback_query(SettingsCallback.filter())
async def process_settings_callback(callback: CallbackQuery, callback_data: SettingsCallback) -> None:
    user_id = callback.from_user.id
    action = callback_data.action

    if action == "toggle_notify":
        user = await _ensure_user(user_id)
        new_active = not user["is_active"]
        await db.toggle_user_active(user_id, new_active)

    elif action == "clear_threshold":
        await _ensure_user(user_id)
        await db.clear_threshold(user_id)

    user = await db.get_user(user_id)

    last_rate = await db.get_last_rate()
    text = format_settings_text(user, last_rate, config.CHECK_INTERVAL_MINUTES)
    kb = settings_keyboard(bool(user["is_active"]), bool(user["threshold"]))
    await _safe_edit_text(callback.message, text, kb)
    await callback.answer()