from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.callbacks import ActionCallback


def rate_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏆 Топ-3", callback_data=ActionCallback(action="top").pack()),
            InlineKeyboardButton(text="📜 История", callback_data=ActionCallback(action="history").pack()),
        ]
    ])