from aiogram import Router, types
from aiogram.filters import Command
from database import db

router = Router()


@router.message(Command("orders"))
async def cmd_orders(message: types.Message):
    # simple list of open orders (for testing)
    cur = await db.db.execute(
        "SELECT id, cargo, from_addr, to_addr FROM orders "
        "WHERE status = 'WAITING_DRIVER' ORDER BY created_at DESC LIMIT 20"
    )
    rows = await cur.fetchall()
    if not rows:
        await message.answer("Открытых заказов нет.")
        return
    text = "Открытые заказы:\n\n" + "\n".join(
        [f"ID:{r[0]} Cargo:{r[1]} From:{r[2]} To:{r[3]}" for r in rows]
    )
    await message.answer(text)


def register_orders(dp):
    dp.include_router(router)