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


@router.callback_query(F.data.startswith("order_take_"))
async def take_order(callback: CallbackQuery):
    """Handle order taking by driver."""
    order_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    driver_username = callback.from_user.username or "driver"
    
    # Check if driver already has an active order
    cur = await db.db.execute(
        "SELECT active_order FROM users WHERE user_id = ?",
        (driver_id,)
    )
    driver_data = await cur.fetchone()
    
    if driver_data and driver_data[0]:
        await callback.answer("У вас уже есть активный заказ. Сначала завершите его.", show_alert=True)
        return
    
    # Check if order is still available
    cur = await db.db.execute(
        "SELECT status, cargo, from_addr, to_addr, phone FROM orders WHERE id = ?",
        (order_id,)
    )
    order = await cur.fetchone()
    
    if not order or order[0] != "WAITING_DRIVER":
        await callback.answer("Этот заказ уже взят другим водителем.", show_alert=True)
        # Update message to show order is taken (simple update)
        if callback.message:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except:
                pass
        return

    cargo, from_addr, to_addr, phone = order[1], order[2], order[3], order[4]
    
    # Reserve order for 30 minutes
    reserved_until = int((datetime.now() + timedelta(minutes=30)).timestamp())
    
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
    
    # Update the message in the channel
    if callback.message:
        text = (
            f"❗ <b>Заказ взят!</b>\n"
            f"Водитель: @{driver_username}\n"
            f"Ожидается подтверждение в течение 30 минут.\n\n"
            f"📦 <b>Груз:</b> {cargo}\n"
            f"📍 <b>Откуда:</b> {from_addr}\n"
            f"🏁 <b>Куда:</b> {to_addr}\n"
            f"📱 <b>Телефон:</b> {phone}"
        )
        await callback.message.edit_text(
            text=text,
            reply_markup=get_order_taken_keyboard(order_id)
        )
    
    await callback.answer("Вы взяли заказ! У вас есть 30 минут на подтверждение.", show_alert=True)


@router.callback_query(F.data.startswith("order_confirm_"))
async def confirm_order(callback: CallbackQuery):
    """Handle order confirmation by driver."""
    order_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    
    # Verify this driver actually has this order and fetch details
    cur = await db.db.execute("""
        SELECT o.id, o.customer_id, o.phone, u.phone as driver_phone, u.username as driver_username
        FROM orders o
        LEFT JOIN users u ON o.driver_id = u.user_id
        WHERE o.id = ? AND o.driver_id = ?
    """, (order_id, driver_id))
    
    order = await cur.fetchone()
    if not order:
        await callback.answer("Заказ не найден или у вас нет прав для его подтверждения.", show_alert=True)
        return
    
    customer_phone = order[2]
    driver_username = order[4] or "driver"
    
    # Update order status
    await db.db.execute(
        "UPDATE orders SET status = 'completed' WHERE id = ?",
        (order_id,)
    )
    
    # Clear driver's active order
    await db.db.execute(
        "UPDATE users SET active_order = NULL WHERE user_id = ?",
        (driver_id,)
    )
    await db.db.commit()
    
    # Update the message in the channel
    if callback.message:
        text = (
            f"✅ <b>Заказ подтверждён</b>\n"
            f"Водитель: @{driver_username}\n"
            f"Заказчик: {customer_phone}\n"
            f"Больше недоступен."
        )
        await callback.message.edit_text(
            text=text,
            reply_markup=get_order_confirmed_keyboard()
        )
    
    # Notify customer if possible
    try:
        customer_id = order[1]
        driver_phone = order[3] or "не указан"
        await callback.bot.send_message(
            customer_id,
            f"✅ Ваш заказ #{order_id} подтверждён водителем!\n"
            f"Телефон водителя: {driver_phone}"
        )
    except Exception as e:
        print(f"Failed to notify customer: {e}")
    
    await callback.answer("Заказ подтверждён!")


@router.callback_query(F.data.startswith("order_cancel_"))
async def cancel_order(callback: CallbackQuery):
    """Handle order cancellation by driver."""
    order_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    
    # Verify this driver actually has this order and fetch details to restore
    cur = await db.db.execute(
        "SELECT id, customer_id, cargo, from_addr, to_addr, phone FROM orders WHERE id = ? AND driver_id = ?",
        (order_id, driver_id)
    )
    order = await cur.fetchone()
    
    if not order:
        await callback.answer("Заказ не найден или у вас нет прав для его отмены.", show_alert=True)
        return

    cargo, from_addr, to_addr, phone = order[2], order[3], order[4], order[5]
    
    # Update order status back to created (which corresponds to 'created' in generic logic, or 'created'/'open' in context)
    # The original status was 'created' in create_order, but logic seems to use 'created' or 'open'.
    # create_order sets 'WAITING_DRIVER'. 'status' column default is 'created'.
    # 'take_order' check checks for 'open' (Wait, logic in take_order checked for != 'open').
    # Let's check statuses in states.py or database setup.
    # database lines: status TEXT NOT NULL DEFAULT 'created'
    # orders.py: WHERE status = 'open'
    # customer.py: sets OrderStatus.WAITING_DRIVER.name => "WAITING_DRIVER"
    # So I should set it back to "WAITING_DRIVER" or "created".
    # And check why take_order checks 'open'.
    # take_order line 57: `if not order or order[0] != "open":`
    # This implies 'open' is the status for available orders.
    # But customer.py inserts `OrderStatus.WAITING_DRIVER.name`.
    # Let's look at states.py. `WAITING_DRIVER` = auto().
    # .name will be 'WAITING_DRIVER'.
    # So `take_order` checking "open" might be a BUG in the existing code if 'WAITING_DRIVER' is used.
    # I should check what customer.py inserts.
    # customer.py line 199: `OrderStatus.WAITING_DRIVER.name`
    # So status is "WAITING_DRIVER".
    # take_order checks `order[0] != "open"`.
    # This is a Logic Error in the original code. I should fix it to 'WAITING_DRIVER'.
    
    # Reverting to 'WAITING_DRIVER'
    await db.db.execute(
        "UPDATE orders SET status = ?, driver_id = NULL, reserved_until = NULL WHERE id = ?",
        ('WAITING_DRIVER', order_id)
    )
    
    # Clear driver's active order
    await db.db.execute(
        "UPDATE users SET active_order = NULL WHERE user_id = ?",
        (driver_id,)
    )
    await db.db.commit()
    
    # Update the message in the channel - Restore original card
    if callback.message:
        text = (
            f"🚚 <b>Новый заказ #{order_id}</b>\n\n"
            f"📦 <b>Груз:</b> {cargo}\n"
            f"📍 <b>Откуда:</b> {from_addr}\n"
            f"🏁 <b>Куда:</b> {to_addr}\n"
            f"📱 <b>Телефон:</b> {phone}"
        )
        await callback.message.edit_text(
            text=text,
            reply_markup=get_order_keyboard(order_id)
        )
    
    # Notify customer if possible
    try:
        customer_id = order[1]
        await callback.bot.send_message(
            customer_id,
            f"❌ Водитель отказался от заказа #{order_id}.\n"
            "Ваш заказ снова доступен для других водителей."
        )
    except Exception as e:
        print(f"Failed to notify customer: {e}")
    
    await callback.answer("Вы отказались от заказа.")


@router.message(Command("me"))
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