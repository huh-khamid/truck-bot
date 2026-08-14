from aiogram import Router, types, F
from aiogram.filters import Command
from database import db

router = Router()

@router.message(Command("orders"))
@router.message(F.text == "🚚 Найти заказы")
async def cmd_orders(message: types.Message):
    # simple list of open orders
    cur = await db.db.execute(
        "SELECT id, cargo, from_addr, to_addr FROM orders "
        "WHERE status = 'WAITING_DRIVER' ORDER BY created_at DESC LIMIT 20"
    )
    rows = await cur.fetchall()
    if not rows:
        await message.answer("Открытых заказов пока нет.")
        return
    text = "🚚 <b>Открытые заказы:</b>\n\n" + "\n\n".join(
        [f"📦 <b>Заказ #{r[0]}</b>\nГруз: {r[1]}\nОткуда: {r[2]}\nКуда: {r[3]}" for r in rows]
    )
    await message.answer(text)

@router.message(F.text == "📋 Мои заказы")
async def cmd_my_orders(message: types.Message):
    user_id = message.from_user.id
    cur = await db.db.execute(
        "SELECT id, cargo, status FROM orders "
        "WHERE customer_id = ? ORDER BY created_at DESC LIMIT 10",
        (user_id,)
    )
    rows = await cur.fetchall()
    if not rows:
        await message.answer("Вы еще не создавали заказов.")
        return
    text = "📋 <b>Ваши последние заказы:</b>\n\n" + "\n".join(
        [f"📦 <b>#{r[0]}</b> - {r[1]} ({r[2]})" for r in rows]
    )
    await message.answer(text)

def register_orders(dp):
    dp.include_router(router)