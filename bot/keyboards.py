from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from bot.callbacks import CityCallback, MenuCallback, PageCallback, SettingsCallback


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Курсы"), KeyboardButton(text="🏆 Топ-3")],
            [KeyboardButton(text="📜 История"), KeyboardButton(text="🌆 Город")],
            [KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
    )


def city_keyboard(current_city: str) -> InlineKeyboardMarkup:
    labels = {"gomel": "Гомель", "minsk": "Минск"}
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=("✅ " if city == current_city else "") + name,
            callback_data=CityCallback(city=city).pack(),
        ) for city, name in labels.items()]
    ])


def rate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏆 Топ-3", callback_data=MenuCallback(action="top").pack()),
            InlineKeyboardButton(text="📜 История", callback_data=MenuCallback(action="history").pack()),
        ],
    ])


def top_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Все курсы", callback_data=MenuCallback(action="rate").pack()),
            InlineKeyboardButton(text="📜 История", callback_data=MenuCallback(action="history").pack()),
        ],
    ])


def history_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Все курсы", callback_data=MenuCallback(action="rate").pack()),
            InlineKeyboardButton(text="🏆 Топ-3", callback_data=MenuCallback(action="top").pack()),
        ],
    ])


def pagination_keyboard(action: str, current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Navigation buttons: ← | Page X/Y | →"""
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    if current_page > 1:
        row.append(
            InlineKeyboardButton(
                text="←", callback_data=PageCallback(action=action, page=current_page - 1).pack()
            )
        )

    row.append(
        InlineKeyboardButton(
            text=f"Стр {current_page}/{total_pages}", callback_data="noop"
        )
    )

    if current_page < total_pages:
        row.append(
            InlineKeyboardButton(
                text="→", callback_data=PageCallback(action=action, page=current_page + 1).pack()
            )
        )

    buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def settings_keyboard(is_active: bool, has_threshold: bool) -> InlineKeyboardMarkup:
    notify_text = "🔕 Выключить уведомления" if is_active else "🔔 Включить уведомления"
    rows = [
        [InlineKeyboardButton(text=notify_text, callback_data=SettingsCallback(action="toggle_notify").pack())],
    ]
    if has_threshold:
        rows.append(
            [InlineKeyboardButton(text="❌ Сбросить порог", callback_data=SettingsCallback(action="clear_threshold").pack())],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
