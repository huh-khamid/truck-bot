from aiogram import Router, types
from aiogram.filters import CommandStart
from keyboards.auth_buttons import role_keyboard
from database import db

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id

    # проверяем, есть ли уже роль в БД
    cur = await db.db.execute(
        "SELECT role FROM users WHERE user_id = ?",
        (user_id,),
    )
    row = await cur.fetchone()
    role = row[0] if row else None

    if role:
        # роль уже есть — не просим выбирать заново
        await message.answer(
            f"Привет! Твоя текущая роль: <b>{role}</b>.\n\n"
            "Чтобы сменить роль, напиши команду /role.\n"
            "Чтобы оформить заказ, напиши команду /order."
        )
    else:
        # роли нет — показываем выбор
        await message.answer(
            "Привет! Выбери роль:",
            reply_markup=role_keyboard()
        )


def register_start(dp):
    dp.include_router(router)