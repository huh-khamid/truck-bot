from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from config import CAR_MODELS


def role_keyboard():
    """Create keyboard for role selection."""
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Заказчик", callback_data="role_customer")
    kb.button(text="🚚 Водитель", callback_data="role_driver")
    kb.adjust(2)
    return kb.as_markup()


def phone_keyboard():
    """Create keyboard for phone number request."""
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return kb


def car_models_keyboard():
    """Create inline keyboard for car model selection."""
    kb = InlineKeyboardBuilder()
    for model_id, model_name in CAR_MODELS:
        kb.button(text=model_name, callback_data=f"car_{model_id}")
    kb.adjust(2)
    return kb.as_markup()


def confirm_order_keyboard(order_id: int):
    """Create inline keyboard for order confirmation."""
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить заказ", callback_data=f"order_confirm_{order_id}")
    kb.button(text="❌ Отменить заказ", callback_data=f"order_cancel_{order_id}")
    kb.adjust(1)
    return kb.as_markup()


def order_taken_keyboard(driver_username: str = None):
    """Create message for taken order."""
    if driver_username:
        return f"✅ Заказ взят водителем @{driver_username}"
    return "✅ Заказ взят водителем"