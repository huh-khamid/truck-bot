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

logger = logging.getLogger(__name__)

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
    logger.info(f"Current WEBHOOK_URL value: '{WEBHOOK_URL}'")
    if WEBHOOK_URL:
        try:
            await bot.set_webhook(WEBHOOK_URL)
            info = await bot.get_webhook_info()
            logger.info(f"Webhook set successfully. Info: {info}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
    else:
        logger.warning("WEBHOOK_URL is missing or empty!")
    logging.info("Startup done")


@app.get("/")
async def root():
    return {
        "status": "online", 
        "webhook_configured": bool(WEBHOOK_URL),
        "docs": "/docs"
    }


@app.get("/debug")
async def debug_info():
    try:
        info = await bot.get_webhook_info()
        return {
            "webhook_info": {
                "url": info.url,
                "has_custom_certificate": info.has_custom_certificate,
                "pending_update_count": info.pending_update_count,
                "last_error_date": info.last_error_date,
                "last_error_message": info.last_error_message,
            }
        }
    except Exception as e:
        return {"error": str(e)}


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