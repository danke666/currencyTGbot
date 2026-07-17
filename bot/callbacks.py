from aiogram.filters.callback_data import CallbackData


class MenuCallback(CallbackData, prefix="menu"):
    action: str


class DashboardCallback(CallbackData, prefix="dash"):
    action: str


class SettingsCallback(CallbackData, prefix="settings"):
    action: str


class CityCallback(CallbackData, prefix="city"):
    city: str


class PageCallback(CallbackData, prefix="page"):
    action: str  # "rate" | "history"
    page: int
