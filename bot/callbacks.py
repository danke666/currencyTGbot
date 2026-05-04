from aiogram.filters.callback_data import CallbackData


class ActionCallback(CallbackData, prefix="act"):
    action: str