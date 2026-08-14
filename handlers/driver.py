import time
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from database import db
from config import ORDERS_CHANNEL_ID, CAR_MODELS
from keyboards.order_buttons import get_order_taken_keyboard, get_order_keyboard, get_order_confirmed_keyboard
from keyboards.driver_buttons import get_car_models_keyboard

router = Router()


@router.callback_query(F.data.startswith("car_"))
async def set_car_model(callback: CallbackQuery):
    """Handle car model selection."""
    model_id = callback.data.split("_", 1)[1]
    model_name = next((name for id, name in CAR_MODELS if id == model_id), "Неизвестно")
    
    await db.db.execute(
        "UPDATE users SET car_model = ? WHERE user_id = ?",
        (model_name, callback.from_user.id)
    )
    await db.db.commit()
    
    await callback.answer(f"Выбрана машина: {model_name}")
    await callback.message.answer(
        f"Отлично! Ваша машина: <b>{model_name}</b>\n"
        "Теперь вы можете принимать заказы."
    )


async def start_taking_order(message: Message, order_id: int):
    """Handle the start of taking an order (triggered via deep link)."""
    driver_id = message.from_user.id
    driver_username = message.from_user.username or "driver"
    bot = message.bot
    
    # Check if user is a driver
    cur = await db.db.execute("SELECT role, active_order FROM users WHERE user_id = ?", (driver_id,))
    user_data = await cur.fetchone()
    
    if not user_data or user_data[0] != "driver":
        await message.answer("❌ Вы не зарегистрированы как водитель. Нажмите /start и выберите роль.")
        return

    if user_data[1]:
        await message.answer("❌ У вас уже есть активный заказ. Сначала завершите его.")
        return

    # Check order availability
    cur = await db.db.execute(
        "SELECT status, cargo, from_addr, to_addr, phone, tg_message_id FROM orders WHERE id = ?",
        (order_id,)
    )
    order = await cur.fetchone()
    
    if not order or order[0] != "WAITING_DRIVER":
        await message.answer("❌ Этот заказ уже взят другим водителем или отменен.")
        return

    cargo, from_addr, to_addr, phone, tg_message_id = order[1], order[2], order[3], order[4], order[5]

    # Reserve order
    reserved_until = int((datetime.now() + timedelta(minutes=15)).timestamp())
    
    await db.db.execute("""
        UPDATE orders 
        SET status = 'reserved',
            driver_id = ?,
            reserved_until = ?
        WHERE id = ?
    """, (driver_id, reserved_until, order_id))
    
    await db.db.execute(
        "UPDATE users SET active_order = ? WHERE user_id = ?",
        (order_id, driver_id)
    )
    await db.db.commit()
    
    # Update Channel Message
    try:
        from config import ORDERS_CHANNEL_ID
        channel_text = (
            f"❗ <b>Заказ обрабатывается...</b>\n"
            f"Водитель: @{driver_username}\n\n"
            f"📦 <b>Груз:</b> {cargo}\n"
            f"📍 <b>Откуда:</b> {from_addr}\n"
            f"🏁 <b>Куда:</b> {to_addr}"
        )
        # Remove buttons from channel message while processing
        await bot.edit_message_text(
            chat_id=ORDERS_CHANNEL_ID,
            message_id=tg_message_id,
            text=channel_text,
            reply_markup=None
        )
    except Exception as e:
        print(f"Error updating channel message: {e}")

    # Send Private Message to Driver
    text = (
        f"✅ <b>Вы начали оформление заказа #{order_id}</b>\n\n"
        f"📦 <b>Груз:</b> {cargo}\n"
        f"📍 <b>Откуда:</b> {from_addr}\n"
        f"🏁 <b>Куда:</b> {to_addr}\n"
        f"📱 <b>Телефон заказчика:</b> {phone}\n\n"
        f"⏳ <b>У вас есть 15 минут</b>, чтобы принять решение."
    )
    await message.answer(text, reply_markup=get_order_taken_keyboard(order_id))


@router.callback_query(F.data.startswith("order_take_"))
async def take_order_deprecated(callback: CallbackQuery):
    """Deprecated callback handler (kept for backward compatibility or accidental clicks on old buttons)."""
    await callback.answer("Пожалуйста, используйте новую кнопку (ссылку) в канале.", show_alert=True)


@router.callback_query(F.data.startswith("order_confirm_"))
async def confirm_order(callback: CallbackQuery):
    """Handle order confirmation by driver from private chat."""
    order_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    
    # Verify order and fetch details including tg_message_id for channel update
    cur = await db.db.execute("""
        SELECT o.id, o.customer_id, o.phone, u.phone as driver_phone, u.username as driver_username, o.tg_message_id
        FROM orders o
        LEFT JOIN users u ON o.driver_id = u.user_id
        WHERE o.id = ? AND o.driver_id = ?
    """, (order_id, driver_id))
    
    order = await cur.fetchone()
    if not order:
        await callback.answer("Заказ не найден или истекло время.", show_alert=True)
        return
    
    customer_id, customer_phone, driver_phone, driver_username, tg_message_id = order[1], order[2], order[3], order[4] or "driver", order[5]
    
    # Update order status
    await db.db.execute(
        "UPDATE orders SET status = 'completed' WHERE id = ?",
        (order_id,)
    )
    
    # Clear active order
    await db.db.execute(
        "UPDATE users SET active_order = NULL WHERE user_id = ?",
        (driver_id,)
    )
    await db.db.commit()
    
    # Update Private Message
    await callback.message.edit_text(
        f"✅ <b>Заказ #{order_id} успешно подтверждён!</b>\n"
        f"Телефон заказчика: {customer_phone}\n\n"
        "Свяжитесь с заказчиком как можно скорее.",
        reply_markup=None
    )
    
    # Update Channel Message
    try:
        from config import ORDERS_CHANNEL_ID
        channel_text = (
            f"✅ <b>Заказ выполнен</b>\n"
            f"Водитель: @{driver_username}\n"
            f"Больше недоступен."
        )
        await callback.bot.edit_message_text(
            chat_id=ORDERS_CHANNEL_ID,
            message_id=tg_message_id,
            text=channel_text,
            reply_markup=get_order_confirmed_keyboard()
        )
    except Exception as e:
        print(f"Failed to update channel: {e}")
    
    # Notify Customer
    try:
        await callback.bot.send_message(
            customer_id,
            f"✅ Ваш заказ #{order_id} подтверждён водителем!\n"
            f"Телефон водителя: {driver_phone}"
        )
    except Exception as e:
        print(f"Failed to notify customer: {e}")
    
    await callback.answer()


@router.callback_query(F.data.startswith("order_cancel_"))
async def cancel_order(callback: CallbackQuery):
    """Handle order cancellation by driver from private chat."""
    order_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    
    # Verify and fetch details to restore channel post
    cur = await db.db.execute(
        "SELECT id, customer_id, cargo, from_addr, to_addr, phone, tg_message_id FROM orders WHERE id = ? AND driver_id = ?",
        (order_id, driver_id)
    )
    order = await cur.fetchone()
    
    if not order:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    cargo, from_addr, to_addr, phone, tg_message_id = order[2], order[3], order[4], order[5], order[6]
    
    # Restore status to WAITING_DRIVER
    await db.db.execute(
        "UPDATE orders SET status = ?, driver_id = NULL, reserved_until = NULL WHERE id = ?",
        ('WAITING_DRIVER', order_id)
    )
    
    # Clear active order
    await db.db.execute(
        "UPDATE users SET active_order = NULL WHERE user_id = ?",
        (driver_id,)
    )
    await db.db.commit()
    
    # Update Private Message
    await callback.message.edit_text(
        "❌ Вы отказались от выполнения заказа.",
        reply_markup=None
    )
    
    # Restore Channel Message
    try:
        from config import ORDERS_CHANNEL_ID
        from main import bot_info
        from keyboards.order_buttons import get_order_keyboard
        
        bot_username = bot_info.get("username", "truck_bot")
        channel_text = (
            f"🚚 <b>Новый заказ #{order_id}</b>\n\n"
            f"📦 <b>Груз:</b> {cargo}\n"
            f"📍 <b>Откуда:</b> {from_addr}\n"
            f"🏁 <b>Куда:</b> {to_addr}\n"
            f"📱 <b>Телефон:</b> {phone}"
        )
        await callback.bot.edit_message_text(
            chat_id=ORDERS_CHANNEL_ID,
            message_id=tg_message_id,
            text=channel_text,
            reply_markup=get_order_keyboard(order_id, bot_username)
        )
    except Exception as e:
        print(f"Failed to restore channel message: {e}")
    
    await callback.answer()


@router.message(Command("me"))
@router.message(F.text == "👤 Мой профиль")
async def cmd_me(message: types.Message):
    """Show driver's current status and active order."""
    cur = await db.db.execute("""
        SELECT u.role, u.car_model, u.active_order, 
               o.cargo, o.from_addr, o.to_addr, o.status
        FROM users u
        LEFT JOIN orders o ON u.active_order = o.id
        WHERE u.user_id = ?
    """, (message.from_user.id,))
    
    row = await cur.fetchone()
    if not row:
        await message.answer("Вы не зарегистрированы. Нажмите /start и выберите роль.")
        return
    
    role, car_model, active_order, cargo, from_addr, to_addr, status = row
    
    text = (
        f"👤 <b>Ваш профиль</b>\n"
        f"Роль: {role}\n"
        f"Машина: {car_model or 'не указана'}\n"
    )
    
    if active_order:
        text += (
            "\n🚚 <b>Активный заказ</b>\n"
            f"Груз: {cargo}\n"
            f"Откуда: {from_addr}\n"
            f"Куда: {to_addr}\n"
            f"Статус: {status}"
        )
    
    await message.answer(text)


def register_driver(dp):
    dp.include_router(router)