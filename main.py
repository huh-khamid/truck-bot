import asyncio
import json
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from config import BOT_TOKEN, WEBHOOK_URL
from database import db
import logging

# handlers registration
from handlers.start import register_start
from handlers.auth import register_auth
from handlers.customer import register_customer
from handlers.driver import register_driver
from handlers.orders import register_orders

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

app = FastAPI()

# include handlers
register_start(dp)
register_auth(dp)
register_customer(dp)
register_driver(dp)
register_orders(dp)


@app.on_event("startup")
async def startup():
    await db.connect()
    # set webhook on startup if WEBHOOK_URL provided
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)
    logging.info("Startup done")


@app.post("/")
async def telegram_webhook(request: Request):
    try:
        update_json = await request.json()
    except json.JSONDecodeError:
        # Пришёл невалидный JSON (health‑check или мусор) — просто отвечаем 200,
        # чтобы не засорять логи 500‑ками.
        return {"ok": True}

    # На всякий случай отсечём странные тела без update_id
    if not isinstance(update_json, dict) or "update_id" not in update_json:
        return {"ok": True}

    update = Update(**update_json)
    await dp.feed_update(bot, update)
    return {"ok": True}