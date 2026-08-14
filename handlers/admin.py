import asyncio
from aiogram import Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import ADMINS
from database import db
from states import AdminState
from keyboards.admin import get_admin_keyboard, get_cancel_admin_keyboard

async def admin_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return
    
    await state.clear()
    await message.answer("Добро пожаловать в админ-панель!", reply_markup=get_admin_keyboard())

async def show_statistics(message: Message):
    if message.from_user.id not in ADMINS:
        return

    stats = await db.get_stats()
    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: {stats.get('total_users', 0)}\n"
        f"👤 Клиентов: {stats.get('customers', 0)}\n"
        f"🚚 Водителей: {stats.get('drivers', 0)}\n\n"
        f"📦 Всего заказов: {stats.get('total_orders', 0)}\n"
        f"⏳ Активных заказов: {stats.get('active_orders', 0)}"
    )
    await message.answer(text, reply_markup=get_admin_keyboard())

async def broadcast_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return
    
    await state.set_state(AdminState.waiting_for_broadcast_message)
    await message.answer(
        "Введите сообщение для рассылки всем пользователям бота:\n\n"
        "<i>Поддерживается текст, фото, видео и т.д.</i>",
        reply_markup=get_cancel_admin_keyboard()
    )

async def cancel_broadcast(message: Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return

    await state.clear()
    await message.answer("Рассылка отменена.", reply_markup=get_admin_keyboard())

async def broadcast_send(message: Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return
    
    users = await db.get_all_users()
    if not users:
        await message.answer("Пользователей не найдено.")
        await state.clear()
        return

    await message.answer("🚀 Рассылка начата...")
    await state.clear()

    success = 0
    failed = 0
    for user_id in users:
        try:
            await message.copy_to(user_id)
            success += 1
            await asyncio.sleep(0.05)  # Anti-flood delay
        except Exception:
            failed += 1
    
    await message.answer(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"Успешно: {success}\n"
        f"Ошибок (заблокировали бота): {failed}",
        reply_markup=get_admin_keyboard()
    )

def register_admin(dp: Dispatcher):
    dp.message.register(admin_start, Command("admin"))
    dp.message.register(show_statistics, F.text == "📊 Статистика")
    dp.message.register(broadcast_start, F.text == "📢 Рассылка")
    dp.message.register(cancel_broadcast, F.text == "Отмена рассылки", AdminState.waiting_for_broadcast_message)
    dp.message.register(broadcast_send, AdminState.waiting_for_broadcast_message)
