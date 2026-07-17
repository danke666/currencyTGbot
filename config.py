import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
PARSER_URL: str = os.getenv("PARSER_URL", "https://myfin.by/currency/usdrub/gomel")
MINSK_PARSER_URL: str = os.getenv(
    "MINSK_PARSER_URL", "https://myfin.by/currency/usdrub"
)
CITY_URLS: dict[str, str] = {
    "gomel": PARSER_URL,
    "minsk": MINSK_PARSER_URL,
}
CITY_NAMES: dict[str, str] = {
    "gomel": "Гомель",
    "minsk": "Минск",
}
PAIR_URLS: dict[str, str] = {
    "usd": "https://myfin.by/currency/usd",
    "eur": "https://myfin.by/currency/eur",
    "rub": "https://myfin.by/currency/rub",
    "usdrub": PARSER_URL,
}
DEFAULT_CITY: str = os.getenv("DEFAULT_CITY", "gomel").lower()
if DEFAULT_CITY not in CITY_URLS:
    DEFAULT_CITY = "gomel"
CHECK_INTERVAL_MINUTES: int = int(os.getenv("CHECK_INTERVAL_MINUTES", "10"))
_volume_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
DATABASE_PATH: str = os.getenv("DATABASE_PATH") or (
    os.path.join(_volume_path, "bot.db") if _volume_path else "data/bot.db"
)
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
