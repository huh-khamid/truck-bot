from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, 
    Message, 
    ReplyKeyboardMarkup, 
    KeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, StateFilter
from aiogram.exceptions import TelegramBadRequest
import logging

from database import db
from keyboards.auth_buttons import role_keyboard as get_role_keyboard
from keyboards.driver_buttons import get_car_models_keyboard

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

class AuthState(StatesGroup):
    """Состояния процесса аутентификации пользователя."""
    waiting_for_phone = State()      # Ожидание номера телефона
    waiting_for_car_model = State()  # Ожидание выбора модели автомобиля


@router.message(Command("role"))
async def cmd_role(message: Message):
    """Обработчик команды /role для выбора роли пользователя."""
    try:
        await message.answer(
            "👤 <b>Выберите вашу роль:</b>", 
            reply_markup=get_role_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in cmd_role: {e}")
        await message.answer("❌ Произошла ошибка. Пожалуйста, попробуйте снова.")


@router.callback_query(F.data.startswith("role_"))
async def set_role(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора роли пользователя."""
    try:
        role = callback.data.split("_", 1)[1]  # Безопасное разделение
        user_id = callback.from_user.id
        
        if role not in ["customer", "driver"]:
            await callback.answer("❌ Неверная роль")
            return
        
        # Обновление роли в базе данных
        await db.db.execute(
            """
            INSERT INTO users (user_id, role, created_at) 
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET role = excluded.role
            """,
            (user_id, role)
        )
        await db.db.commit()
        
        if role == "driver":
            # Для водителей запрашиваем модель автомобиля
            await state.set_state(AuthState.waiting_for_car_model)
            await callback.message.answer(
                "🚗 <b>Выберите модель вашего автомобиля:</b>",
                reply_markup=get_car_models_keyboard()
            )
        else:
            # Для заказчиков запрашиваем номер телефона
            await state.set_state(AuthState.waiting_for_phone)
            await callback.message.answer(
                "📱 <b>Поделитесь вашим номером телефона</b> (нажмите кнопку ниже):",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[
                        KeyboardButton(
                            text="📱 Отправить номер", 
                            request_contact=True
                        )
                    ]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
            )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in set_role: {e}")
        try:
            await callback.answer("❌ Ошибка при выборе роли")
        except:
            pass


@router.message(AuthState.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    """Обработчик ввода номера телефона."""
    try:
        # Получаем номер телефона из контакта или текста
        phone = (
            message.contact.phone_number 
            if message.contact and message.contact.phone_number
            else message.text
        )
        
        if not phone:
            await message.answer("❌ Номер телефона не может быть пустым. Попробуйте снова:")
            return
            
        # Сохраняем номер в базу данных
        await db.db.execute(
            "UPDATE users SET phone = ? WHERE user_id = ?",
            (phone, message.from_user.id)
        )
        await db.db.commit()
        
        # Получаем роль пользователя для персонализированного сообщения
        cur = await db.db.execute(
            "SELECT role FROM users WHERE user_id = ?",
            (message.from_user.id,)
        )
        role_row = await cur.fetchone()
        role = role_row[0] if role_row else "пользователь"
        
        role_name = "водитель" if role == "driver" else "заказчик"
        
        await message.answer(
            f"✅ <b>Регистрация завершена!</b>\n\n"
            f"👤 <b>Ваша роль:</b> {role_name}\n"
            f"📱 <b>Телефон:</b> {phone}\n\n"
            "Используйте /help для просмотра доступных команд.",
            reply_markup=ReplyKeyboardRemove()
         )
        
    except Exception as e:
        logger.error(f"Error in process_phone: {e}")
        await message.answer(
            "❌ Произошла ошибка при обработке номера. Пожалуйста, попробуйте снова."
        )
    finally:
        await state.clear()


@router.callback_query(F.data.startswith("car_"))
async def set_car_model(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора модели автомобиля."""
    try:
        car_model = callback.data.split("_", 1)[1]
        user_id = callback.from_user.id
        
        # Сохраняем модель автомобиля в базу данных
        await db.db.execute(
            "UPDATE users SET car_model = ? WHERE user_id = ?",
            (car_model, user_id)
        )
        await db.db.commit()
        
        # Запрашиваем номер телефона
        await state.set_state(AuthState.waiting_for_phone)
        await callback.message.answer(
            "📱 <b>Отлично! Теперь поделитесь вашим номером телефона</b> (нажмите кнопку ниже):",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[
                    KeyboardButton(
                        text="📱 Отправить номер", 
                        request_contact=True
                    )
                ]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        
        await callback.answer(f"Выбрана модель: {car_model}")
        
    except Exception as e:
        logger.error(f"Error in set_car_model: {e}")
        try:
            await callback.answer("❌ Ошибка при выборе модели")
        except:
            pass


def register_auth(dp):
    """Регистрация обработчиков аутентификации."""
    dp.include_router(router)