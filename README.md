# Currency Telegram Bot

Telegram-бот показывает курсы USD/RUB банков Гомеля и Минска и отправляет
уведомления об изменениях и достижении пользовательского порога.

## Локальный запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

В `.env` необходимо заполнить `BOT_TOKEN`, полученный у `@BotFather`.

## Railway

1. Загрузите репозиторий на GitHub и создайте в Railway проект через
   **Deploy from GitHub repo**.
2. В сервисе откройте **Variables** и добавьте обязательную переменную
   `BOT_TOKEN`. При необходимости добавьте `CHECK_INTERVAL_MINUTES` и
   `LOG_LEVEL`.
3. Подключите к сервису **Volume**. Рекомендуемый mount path: `/data`.
   Бот автоматически сохранит SQLite-базу в `$RAILWAY_VOLUME_MOUNT_PATH/bot.db`.
4. Запустите deployment. Команда `python run.py` уже задана в `railway.json`.

Публичный домен и переменная `PORT` не требуются: Telegram обновления
получаются через long polling. У сервиса должна быть ровно одна реплика, иначе
несколько процессов будут одновременно получать обновления одного бота.

### Переменные окружения

| Переменная | Обязательна | Значение по умолчанию |
|---|---:|---|
| `BOT_TOKEN` | да | — |
| `CHECK_INTERVAL_MINUTES` | нет | `10` |
| `LOG_LEVEL` | нет | `INFO` |
| `DEFAULT_CITY` | нет | `gomel` |
| `DATABASE_PATH` | нет | Volume или `data/bot.db` |
| `PARSER_URL` | нет | URL Гомеля на Myfin |
| `MINSK_PARSER_URL` | нет | URL Минска на Myfin |

База и таблицы создаются автоматически при старте, отдельная команда миграции
не нужна.
