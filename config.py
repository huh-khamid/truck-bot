import os
from typing import List, Tuple

# Telegram Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Telegram bot token
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Full URL for webhook (e.g., https://truckbot.myworkers.dev/)
ORDERS_CHANNEL_ID = os.getenv("ORDERS_CHANNEL_ID")  # Channel ID for posting orders

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///db.sqlite")

# Order Configuration
ORDER_CONFIRMATION_TIMEOUT = 900  # 15 minutes in seconds

# Available Car Models
CAR_MODELS: List[Tuple[str, str]] = [
    ("labo", "Labo"),
    ("porter", "Porter"),
    ("damas", "Damas"),
    ("gazel", "Газель"),
    ("other", "Другая")
]

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Путь на Railway — для локального теста можно оставить пустым