import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardRemove,
    InlineKeyboardMarkup
)
from aiogram.filters import Command, StateFilter

from database import db
from states import OrderState, OrderStatus, Order
from config import ORDERS_CHANNEL_ID, ORDER_CONFIRMATION_TIMEOUT
from keyboards.order_buttons import (
    get_order_keyboard, 
    get_order_taken_keyboard,
    get_order_confirmed_keyboard
)

# Настройка логирования
logger = logging.getLogger(__name__)

router = Router()

# Вспомогательные функции

async def get_user_role(user_id: int) -> str:
    """Получить роль пользователя из базы данных."""
    try:
        cur = await db.db.execute(
            "SELECT role FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"Ошибка при получении роли пользователя {user_id}: {e}")
        return None

async def post_order_to_channel(bot: Bot, order_data: dict, order_id: int) -> int:
    """Опубликовать новый заказ в канале и вернуть ID сообщения."""
    try:
        text = (
            f"🚚 <b>Новый заказ #{order_id}</b>\n\n"
            f"📦 <b>Груз:</b> {order_data.get('cargo', 'Не указан')}\n"
            f"📍 <b>Откуда:</b> {order_data.get('from_addr', 'Не указан')}\n"
            f"🏁 <b>Куда:</b> {order_data.get('to_addr', 'Не указан')}\n"
            f"📱 <b>Телефон:</b> {order_data.get('phone', 'Не указан')}"
        )
        
        # Отправка сообщения в канал
        if not ORDERS_CHANNEL_ID:
            logger.error("ORDERS_CHANNEL_ID is not set!")
            raise ValueError("ORDERS_CHANNEL_ID настроен неправильно (отсутствует).")
            
        logger.info(f"Trying to post to channel ID: {ORDERS_CHANNEL_ID} with text length {len(text)}")
        message = await bot.send_message(
            chat_id=ORDERS_CHANNEL_ID,
            text=text,
            reply_markup=get_order_keyboard(order_id)
        )
        logger.info(f"Successfully posted to channel. Message ID: {message.message_id}")
        return message.message_id
    except Exception as e:
        logger.error(f"Ошибка при публикации заказа #{order_id} в канал (ID: {ORDERS_CHANNEL_ID}): {e}")
        raise

async def get_order(order_id: int) -> Optional[Order]:
    """Получить заказ по ID."""
    try:
        cur = await db.db.execute(
            """
            SELECT id, customer_id, cargo, from_addr, to_addr, phone, 
                   status, driver_id, created_at, reserved_until
            FROM orders 
            WHERE id = ?
            """,
            (order_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
            
        return Order(
            order_id=row[0],
            customer_id=row[1],
            cargo=row[2],
            from_addr=row[3],
            to_addr=row[4],
            phone=row[5],
            status=OrderStatus[row[6]] if row[6] else OrderStatus.CREATED,
            driver_id=row[7],
            created_at=datetime.fromtimestamp(row[8]) if row[8] else None,
            reserved_until=datetime.fromtimestamp(row[9]) if row[9] else None
        )
    except Exception as e:
        logger.error(f"Ошибка при получении заказа #{order_id}: {e}")
        return None


@router.message(Command("order"))
@router.message(F.text == "📦 Создать заказ")
async def start_order(message: types.Message, state: FSMContext):
    """Начать процесс создания заказа."""
    # Проверяем, является ли пользователь заказчиком
    role = await get_user_role(message.from_user.id)
    if role != "customer":
        await message.answer("❌ Только заказчики могут создавать заказы.")
        return
    
    # Начинаем процесс создания заказа
    await state.set_state(OrderState.waiting_for_cargo)
    await message.answer(
        "🚛 <b>Оформление нового заказа</b>\n\n"
        "Опишите, что нужно перевезти:"
    )


@router.message(OrderState.waiting_for_cargo)
async def process_cargo(message: Message, state: FSMContext) -> None:
    """Обработка ввода описания груза."""
    await state.update_data(cargo=message.text)
    await state.set_state(OrderState.waiting_for_from)
    await message.answer("📍 Откуда забрать груз? Напишите адрес отправления:")


@router.message(OrderState.waiting_for_from)
async def process_from_address(message: Message, state: FSMContext) -> None:
    """Обработка ввода адреса отправления."""
    await state.update_data(from_addr=message.text)
    await state.set_state(OrderState.waiting_for_to)
    await message.answer("🏁 Куда доставить груз? Напишите адрес доставки:")


@router.message(OrderState.waiting_for_to)
async def process_to_address(message: Message, state: FSMContext) -> None:
    """Обработка ввода адреса доставки."""
    await state.update_data(to_addr=message.text)
    await state.set_state(OrderState.waiting_for_phone)
    
    # Запрашиваем номер телефона
    await message.answer(
        "📱 <b>Поделитесь вашим номером телефона</b> (нажмите кнопку ниже):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )


@router.message(OrderState.waiting_for_phone, F.contact | F.text)
async def process_phone(
    message: Message, 
    state: FSMContext,
    bot: Bot
) -> None:
    """Обработка ввода номера телефона и завершение создания заказа."""
    # Получаем номер телефона из контакта или текста
    if message.contact:
        phone = message.contact.phone_number
    else:
        # Удаляем все нецифровые символы из номера
        phone = ''.join(filter(str.isdigit, message.text))
        if not phone.startswith('+'):
            phone = f'+{phone}'
    
    # Получаем данные из состояния
    data = await state.get_data()
    cargo = data.get('cargo', '').strip()
    from_addr = data.get('from_addr', '').strip()
    to_addr = data.get('to_addr', '').strip()
    
    # Проверяем, что все данные заполнены
    if not all([cargo, from_addr, to_addr, phone]):
        await message.answer(
            "❌ Произошла ошибка. Пожалуйста, начните заново с команды /order",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        return
    
    try:
        # Сохраняем заказ в базу данных
        cur = await db.db.execute(
            """
            INSERT INTO orders (
                customer_id, cargo, from_addr, to_addr, phone, 
                status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                message.from_user.id, 
                cargo, 
                from_addr, 
                to_addr, 
                phone,
                OrderStatus.WAITING_DRIVER.name,
                int(datetime.now().timestamp())
            )
        )
        
        order_id = (await cur.fetchone())[0]
        await db.db.commit()
        
        # Публикуем заказ в канале
        message_id = await post_order_to_channel(
            bot,
            {
                'cargo': cargo,
                'from_addr': from_addr,
                'to_addr': to_addr,
                'phone': phone
            },
            order_id
        )
        
        # Обновляем информацию о сообщении в базе данных
        await db.db.execute(
            """
            UPDATE orders 
            SET tg_chat_id = ?, tg_message_id = ? 
            WHERE id = ?
            """,
            (ORDERS_CHANNEL_ID, message_id, order_id)
        )
        await db.db.commit()
        
        # Отправляем подтверждение пользователю
        await message.answer(
            "✅ <b>Ваш заказ создан и отправлен водителям!</b>\n\n"
            f"<b>Номер заказа:</b> #{order_id}\n"
            f"<b>Груз:</b> {cargo}\n"
            f"<b>Откуда:</b> {from_addr}\n"
            f"<b>Куда:</b> {to_addr}\n"
            f"<b>Телефон:</b> {phone}\n\n"
            "Ожидайте, когда водитель примет ваш заказ.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Сбрасываем состояние
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка при создании заказа: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при создании заказа. Пожалуйста, попробуйте снова.",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()


@router.message(OrderState.waiting_for_phone)
async def process_phone_invalid(message: Message) -> None:
    """Обработка неверного формата номера телефона."""
    await message.answer(
        "❌ Пожалуйста, поделитесь номером телефона, используя кнопку ниже."
    )


@router.callback_query(F.data.startswith("order_status_"))
async def check_order_status(callback: CallbackQuery) -> None:
    """Проверить статус заказа."""
    try:
        order_id = int(callback.data.split("_")[2])
        order = await get_order(order_id)
        
        if not order:
            await callback.answer("❌ Заказ не найден", show_alert=True)
            return
            
        status_text = {
            OrderStatus.CREATED: "создан",
            OrderStatus.WAITING_DRIVER: "ожидает водителя",
            OrderStatus.DRIVER_ASSIGNED: f"взят водителем (ID: {order.driver_id})",
            OrderStatus.IN_PROGRESS: "в процессе доставки",
            OrderStatus.COMPLETED: "завершен",
            OrderStatus.CANCELLED: "отменен",
            OrderStatus.EXPIRED: "истекло время ожидания"
        }.get(order.status, "неизвестен")
        
        await callback.answer(
            f"Статус заказа #{order_id}: {status_text}",
            show_alert=True
        )
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса заказа: {e}")
        await callback.answer("❌ Произошла ошибка при проверке статуса", show_alert=True)


def register_customer(dp):
    """Регистрация обработчиков для заказчиков."""
    dp.include_router(router)