from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_menu(role: str) -> ReplyKeyboardMarkup:
    """Create main menu keyboard based on user role."""
    if role == "customer":
        keyboard = [
            [KeyboardButton(text="📦 Создать заказ")],
            [KeyboardButton(text="📋 Мои заказы"), KeyboardButton(text="👤 Мой профиль")]
        ]
    elif role == "driver":
        keyboard = [
            [KeyboardButton(text="🚚 Найти заказы")],
            [KeyboardButton(text="👤 Мой профиль")]
        ]
    else:
        keyboard = []

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )
