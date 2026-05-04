import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
PARSER_URL: str = os.getenv("PARSER_URL", "https://myfin.by/currency/usdrub/gomel")
CHECK_INTERVAL_MINUTES: int = int(os.getenv("CHECK_INTERVAL_MINUTES", "10"))
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/bot.db")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")