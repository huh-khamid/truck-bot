from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def get_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Create inline keyboard for a new order."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Взять заказ",
        callback_data=f"order_take_{order_id}"
    )
    return builder.as_markup()

def get_order_taken_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Create inline keyboard for a taken order (confirm/cancel)."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Подтвердить",
            callback_data=f"order_confirm_{order_id}"
        ),
        InlineKeyboardButton(
            text="❌ Отменить",
            callback_data=f"order_cancel_{order_id}"
        )
    )
    return builder.as_markup()

def get_order_confirmed_keyboard() -> InlineKeyboardMarkup:
    """Create a simple 'Order Confirmed' message without any buttons."""
    builder = InlineKeyboardBuilder()
    return builder.as_markup()

