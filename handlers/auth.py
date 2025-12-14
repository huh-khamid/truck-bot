from aiogram import Router, types
from aiogram.filters import Command
from database import db
from keyboards.auth_buttons import role_keyboard

router = Router()


@router.message(Command("role"))
async def cmd_role(message: types.Message):
    # показать клавиатуру выбора роли заново
    await message.answer("Выбери новую роль:", reply_markup=role_keyboard())


@router.callback_query(lambda c: c.data and c.data.startswith("role_"))
async def cb_set_role(callback: types.CallbackQuery):
    role = callback.data.split("_", 1)[1]
    user_id = callback.from_user.id
    await db.set_role(user_id, role)
    await callback.answer("Роль сохранена")
    await callback.message.answer(f"Вы выбрали роль: <b>{role}</b>")


def register_auth(dp):
    dp.include_router(router)