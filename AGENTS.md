# Agents

## Project

Telegram bot für USD/RUB Wechselkurse in Gomel (Belarus). Parst myfin.by, findet den besten Verkaufspreis und benachrichtigt Nutzer bei Schwellenwert-Überschreitung.

## Stack

- Python 3.11+, aiogram 3, aiohttp, BeautifulSoup4 (lxml), aiosqlite
- DB: SQLite (async via aiosqlite) at `data/bot.db`

## Architecture

```
bot/        — Telegram handlers, notifier, entry point
services/   — parser (myfin.by scraping), rate_service (business logic)
database/   — SQLite CRUD (users, rate_history)
utils/      — logging setup
config.py   — env-based config (.env)
run.py      — asyncio entrypoint
```

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill BOT_TOKEN

# Run
python run.py
```

## Key facts

- myfin.by loads currency data via JS — parser uses a text-extraction fallback when CSS selectors miss the dynamic table
- `config.PARSER_URL` defaults to `https://myfin.by/currency/usdrub/gomel`; changeable via `.env`
- Notification loop interval: `CHECK_INTERVAL_MINUTES` env var (default 10)
- Threshold of 0 means disabled; users set it via `/set_threshold`
- DB auto-creates on first run — no migration step needed