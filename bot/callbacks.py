from aiogram.filters.callback_data import CallbackData


class MenuCallback(CallbackData, prefix="menu"):
    action: str


class SettingsCallback(CallbackData, prefix="settings"):
    action: str


class PageCallback(CallbackData, prefix="page"):
    action: str  # "rate" | "history"
    page: int