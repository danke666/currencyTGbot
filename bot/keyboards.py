from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from bot.callbacks import CityCallback, DashboardCallback, MenuCallback, PageCallback, SettingsCallback


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Панель"), KeyboardButton(text="📊 Курсы")],
            [KeyboardButton(text="🏆 Топ-3"), KeyboardButton(text="🧮 Калькулятор")],
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
        [InlineKeyboardButton(text="🏠 Панель", callback_data=DashboardCallback(action="home").pack())],
    ])


def dashboard_keyboard(is_active: bool, has_threshold: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Курсы", callback_data=DashboardCallback(action="rates").pack()),
         InlineKeyboardButton(text="🏆 Топ-3", callback_data=DashboardCallback(action="top").pack())],
        [InlineKeyboardButton(text="💵 Продать USD", callback_data=DashboardCallback(action="sell").pack()),
         InlineKeyboardButton(text="🧮 Калькулятор", callback_data=DashboardCallback(action="calc").pack())],
        [InlineKeyboardButton(text="⚖️ Сравнить города", callback_data=DashboardCallback(action="compare").pack()),
         InlineKeyboardButton(text="📈 Статистика", callback_data=DashboardCallback(action="stats").pack())],
        [InlineKeyboardButton(text="🌆 Город", callback_data=DashboardCallback(action="city").pack()),
         InlineKeyboardButton(text="⚙️ Настройки", callback_data=DashboardCallback(action="settings").pack())],
        [InlineKeyboardButton(text=("🔕 Выключить уведомления" if is_active else "🔔 Включить уведомления"),
                              callback_data=DashboardCallback(action="toggle_notify").pack())],
        [InlineKeyboardButton(text="🩺 Состояние", callback_data=DashboardCallback(action="health").pack())],
    ])


def rate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏆 Топ-3", callback_data=MenuCallback(action="top").pack()),
            InlineKeyboardButton(text="📜 История", callback_data=MenuCallback(action="history").pack()),
        ],
        [InlineKeyboardButton(text="🏠 Панель", callback_data=DashboardCallback(action="home").pack())],
    ])


def top_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Все курсы", callback_data=MenuCallback(action="rate").pack()),
            InlineKeyboardButton(text="📜 История", callback_data=MenuCallback(action="history").pack()),
        ],
        [InlineKeyboardButton(text="🏠 Панель", callback_data=DashboardCallback(action="home").pack())],
    ])


def history_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Все курсы", callback_data=MenuCallback(action="rate").pack()),
            InlineKeyboardButton(text="🏆 Топ-3", callback_data=MenuCallback(action="top").pack()),
        ],
        [InlineKeyboardButton(text="🏠 Панель", callback_data=DashboardCallback(action="home").pack())],
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
    rows.append([InlineKeyboardButton(text="🏠 Панель", callback_data=DashboardCallback(action="home").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)
