import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.exceptions import TelegramBadRequest

import config
import database.db as db
from services.rate_service import (
    format_all_rates,
    format_top_rates,
    format_history,
    format_settings_text,
    paginate,
    get_best_rate,
    format_rate_info,
)
from services.rate_service import _esc
from services.parser import parse_bank_rates
from bot.callbacks import CityCallback, DashboardCallback, MenuCallback, PageCallback, SettingsCallback
from bot.keyboards import (
    pagination_keyboard,
    rate_keyboard,
    top_keyboard,
    history_keyboard,
    settings_keyboard,
    city_keyboard,
    calculator_keyboard,
    dashboard_keyboard,
)

logger = logging.getLogger(__name__)

router = Router()

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


async def _user_city(user_id: int) -> str:
    return (await _ensure_user(user_id))["city"]


async def _dashboard_content(user_id: int) -> tuple[str, object]:
    user = await _ensure_user(user_id)
    city = user["city"]
    result = await get_best_rate(config.CITY_URLS[city])
    city_name = config.CITY_NAMES[city]
    if result:
        body = (
            f"🏠 <b>Панель управления</b>\n\n"
            f"Город: <b>{city_name}</b>\n"
            f"Лучший курс покупки: <b>{result.rate} RUB/USD</b>\n"
            f"Банк: {_esc(result.bank)}\n\n"
            f"{format_rate_info(result, city)}"
        )
    else:
        body = f"🏠 <b>Панель управления</b>\n\nГород: <b>{city_name}</b>\n⚠️ Курс временно недоступен"
    return body, dashboard_keyboard(bool(user["is_active"]), bool(user["threshold"]))


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await _ensure_user(message.from_user.id)
    await message.answer("Панель управления открыта.", reply_markup=ReplyKeyboardRemove())
    text, keyboard = await _dashboard_content(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await _safe_delete(message)


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Панель управления открыта.", reply_markup=ReplyKeyboardRemove())
    text, keyboard = await _dashboard_content(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await _safe_delete(message)


@router.message(F.text == "🏠 Панель")
async def btn_dashboard(message: Message) -> None:
    text, keyboard = await _dashboard_content(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await _safe_delete(message)


@router.message(F.text == "🧮 Калькулятор")
async def btn_calculator(message: Message) -> None:
    await message.answer("🧮 Введите сумму долларов командой:\n\n<code>/calc 1000</code>", parse_mode="HTML")
    await _safe_delete(message)


@router.callback_query(DashboardCallback.filter())
async def process_dashboard_callback(callback: CallbackQuery, callback_data: DashboardCallback) -> None:
    action = callback_data.action
    user_id = callback.from_user.id
    user = await _ensure_user(user_id)
    city = user["city"]

    if action == "home":
        text, keyboard = await _dashboard_content(user_id)
        await _safe_edit_text(callback.message, text, keyboard)
    elif action == "city":
        await _safe_edit_text(callback.message, "🌆 Выберите город:", city_keyboard(city))
    elif action == "settings":
        last = await db.get_last_rate(city)
        await _safe_edit_text(
            callback.message,
            format_settings_text(user, last, config.CHECK_INTERVAL_MINUTES),
            settings_keyboard(bool(user["is_active"]), bool(user["threshold"])),
        )
    elif action == "toggle_notify":
        await db.toggle_user_active(user_id, not user["is_active"])
        text, keyboard = await _dashboard_content(user_id)
        await _safe_edit_text(callback.message, text, keyboard)
    elif action in {"rates", "top"}:
        rates = await parse_bank_rates(config.CITY_URLS[city])
        if not rates:
            await callback.answer("Курс временно недоступен", show_alert=True)
        elif action == "rates":
            await _safe_edit_text(callback.message, format_all_rates(rates, city=city), rate_keyboard())
        else:
            await _safe_edit_text(callback.message, format_top_rates(rates, city=city), top_keyboard())
    elif action == "calc":
        await _safe_edit_text(
            callback.message,
            "🧮 <b>Сколько USD хотите купить?</b>\n\n"
            "Выберите сумму или используйте <code>/calc 1234</code>.",
            calculator_keyboard(),
        )
    elif action.startswith("calc_"):
        amount = float(action.removeprefix("calc_"))
        result = await get_best_rate(config.CITY_URLS[city], "buy_usd")
        if not result:
            await callback.answer("Курс временно недоступен", show_alert=True)
        else:
            total = round(amount * result.rate, 2)
            text = (
                f"🧮 <b>Покупка {amount:g} USD</b>\n\n"
                f"{_esc(result.bank)} · <b>{result.rate} RUB/USD</b>\n"
                f"К оплате: <b>{total} RUB</b>"
            )
            await _safe_edit_text(
                callback.message,
                text,
                dashboard_keyboard(bool(user["is_active"]), bool(user["threshold"])),
            )
    await callback.answer()


@router.message(F.text == "📊 Курсы")
async def btn_rates(message: Message) -> None:
    wait_msg = await message.answer("⏳ Получаю курсы...")
    try:
        city = await _user_city(message.from_user.id)
        rates = await parse_bank_rates(config.CITY_URLS[city])
        if not rates:
            await wait_msg.edit_text("Не удалось получить курсы. Попробуйте позже.")
            return
        _, total_pages = paginate([r for r in rates if r.sell is not None], 1)
        text = format_all_rates(rates, page=1, city=city)
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
        city = await _user_city(message.from_user.id)
        rates = await parse_bank_rates(config.CITY_URLS[city])
        if not rates:
            await wait_msg.edit_text("Не удалось получить курсы. Попробуйте позже.")
            return
        text = format_top_rates(rates, city=city)
        await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=top_keyboard())
    except Exception:
        logger.exception("Ошибка при получении курсов")
        await wait_msg.edit_text("Произошла ошибка. Попробуйте позже.")
    finally:
        await _safe_delete(message)


@router.message(F.text == "📜 История")
async def btn_history(message: Message) -> None:
    city = await _user_city(message.from_user.id)
    history = await db.get_rate_history(limit=80, city=city)
    if not history:
        await message.answer("Пока нет данных. Курсы появятся после первой проверки.")
    else:
        _, total_pages = paginate(history, 1)
        text = format_history(history, page=1, city=city)
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

    last_rate = await db.get_last_rate(user["city"])
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
        city = await _user_city(message.from_user.id)
        rates = await parse_bank_rates(config.CITY_URLS[city])
        if not rates:
            await wait_msg.edit_text("Не удалось получить курсы. Попробуйте позже.")
            return
        _, total_pages = paginate([r for r in rates if r.sell is not None], 1)
        text = format_all_rates(rates, page=1, city=city)
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

    last_rate = await db.get_last_rate(user["city"])
    text = format_settings_text(user, last_rate, config.CHECK_INTERVAL_MINUTES)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=settings_keyboard(bool(user["is_active"]), bool(user["threshold"])),
    )
    await _safe_delete(message)


@router.message(Command("calc"))
async def cmd_calc(message: Message) -> None:
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Пример: /calc 1000\nПокажу, сколько RUB нужно для покупки USD.")
        return
    try:
        amount = float(args[1].replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Сумма должна быть положительным числом.")
        return
    city = await _user_city(message.from_user.id)
    result = await get_best_rate(config.CITY_URLS[city], "buy_usd")
    if not result:
        await message.answer("Не удалось получить актуальный курс.")
        return
    total = round(amount * result.rate, 2)
    await message.answer(
        f"🧮 Покупка <b>{amount:g} USD</b> в г. {config.CITY_NAMES[city]}\n\n"
        f"Лучший курс: <b>{result.rate} RUB/USD</b>\n"
        f"Банк: {_esc(result.bank)}\n"
        f"Итого: <b>{total} RUB</b>\n\n{format_rate_info(result, city)}",
        parse_mode="HTML",
    )


@router.message(F.text.lower().in_({"привет", "hello", "hi"}))
async def cmd_hello(message: Message) -> None:
    await _ensure_user(message.from_user.id)
    text, keyboard = await _dashboard_content(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await _safe_delete(message)


# ─── Inline: Main menu callbacks ─────────────────────────────────

@router.callback_query(MenuCallback.filter())
async def process_menu_callback(callback: CallbackQuery, callback_data: MenuCallback) -> None:
    action = callback_data.action
    user_id = callback.from_user.id
    city = await _user_city(user_id)

    if action == "rate":
        try:
            rates = await parse_bank_rates(config.CITY_URLS[city])
        except Exception:
            logger.exception("Ошибка при получении курсов в callback")
            await callback.answer("❌ Не удалось загрузить данные", show_alert=True)
            return
        if not rates:
            await callback.answer("Не удалось получить курсы", show_alert=True)
            return
        _, total_pages = paginate([r for r in rates if r.sell is not None], 1)
        text = format_all_rates(rates, page=1, city=city)
        kb = rate_keyboard()
        if total_pages > 1:
            kb.inline_keyboard.extend(
                pagination_keyboard("rate", 1, total_pages).inline_keyboard
            )
        await _safe_edit_text(callback.message, text, kb)
        await callback.answer()

    elif action == "top":
        try:
            rates = await parse_bank_rates(config.CITY_URLS[city])
        except Exception:
            logger.exception("Ошибка при получении курсов в callback")
            await callback.answer("❌ Не удалось загрузить данные", show_alert=True)
            return
        if not rates:
            await callback.answer("Не удалось получить курсы", show_alert=True)
            return
        text = format_top_rates(rates, city=city)
        await _safe_edit_text(callback.message, text, top_keyboard())
        await callback.answer()

    elif action == "history":
        history = await db.get_rate_history(limit=80, city=city)
        if not history:
            await callback.answer("Пока нет данных", show_alert=True)
            return
        _, total_pages = paginate(history, 1)
        text = format_history(history, page=1, city=city)
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

        last_rate = await db.get_last_rate(city)
        text = format_settings_text(user, last_rate, config.CHECK_INTERVAL_MINUTES)
        kb = settings_keyboard(bool(user["is_active"]), bool(user["threshold"]))
        await _safe_edit_text(callback.message, text, kb)
        await callback.answer()


# ─── Inline: Pagination callbacks ─────────────────────────────────

@router.callback_query(PageCallback.filter())
async def process_page_callback(callback: CallbackQuery, callback_data: PageCallback) -> None:
    action = callback_data.action
    page = callback_data.page
    city = await _user_city(callback.from_user.id)

    if action == "rate":
        try:
            rates = await parse_bank_rates(config.CITY_URLS[city])
        except Exception:
            logger.exception("Ошибка при получении курсов в callback")
            await callback.answer("❌ Не удалось загрузить данные", show_alert=True)
            return
        if not rates:
            await callback.answer("Не удалось получить курсы", show_alert=True)
            return
        valid = [r for r in rates if r.sell is not None]
        _, total_pages = paginate(valid, page)
        text = format_all_rates(rates, page=page, city=city)
        kb = rate_keyboard()
        if total_pages > 1:
            kb.inline_keyboard.extend(
                pagination_keyboard("rate", page, total_pages).inline_keyboard
            )
        await _safe_edit_text(callback.message, text, kb)
        await callback.answer()

    elif action == "history":
        history = await db.get_rate_history(limit=80, city=city)
        if not history:
            await callback.answer("Пока нет данных", show_alert=True)
            return
        _, total_pages = paginate(history, page)
        text = format_history(history, page=page, city=city)
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

    last_rate = await db.get_last_rate(user["city"])
    text = format_settings_text(user, last_rate, config.CHECK_INTERVAL_MINUTES)
    kb = settings_keyboard(bool(user["is_active"]), bool(user["threshold"]))
    await _safe_edit_text(callback.message, text, kb)
    await callback.answer()


@router.message(F.text == "🌆 Город")
async def btn_city(message: Message) -> None:
    city = await _user_city(message.from_user.id)
    await message.answer(
        "🌆 Выберите город для курсов, истории и уведомлений:",
        reply_markup=city_keyboard(city),
    )
    await _safe_delete(message)


@router.callback_query(CityCallback.filter())
async def process_city_callback(callback: CallbackQuery, callback_data: CityCallback) -> None:
    if callback_data.city not in config.CITY_URLS:
        await callback.answer("Неизвестный город", show_alert=True)
        return
    await _ensure_user(callback.from_user.id)
    await db.set_user_city(callback.from_user.id, callback_data.city)
    city_name = config.CITY_NAMES[callback_data.city]
    await _safe_edit_text(
        callback.message,
        f"✅ Выбран город: <b>{city_name}</b>",
        city_keyboard(callback_data.city),
    )
    await callback.answer()
