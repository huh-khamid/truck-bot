from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from config import CAR_MODELS

def get_car_models_keyboard() -> InlineKeyboardMarkup:
    """Create inline keyboard for car model selection."""
    builder = InlineKeyboardBuilder()
    
    for model_id, model_name in CAR_MODELS:
        builder.button(
            text=model_name,
            callback_data=f"car_{model_id}"
        )
    
    builder.adjust(2)  # 2 buttons per row
    return builder.as_markup()
