from aiogram import Router, types
from aiogram.filters import CommandStart, Command, CommandObject
from keyboards.auth_buttons import role_keyboard
from database import db

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    # Check for deep link arguments (e.g. /start take_123)
    args = command.args
    if args and args.startswith("take_"):
        try:
            order_id = int(args.split("_")[1])
            from handlers.driver import start_taking_order
            await start_taking_order(message, order_id)
            return
        except ValueError:
            pass

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


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "🆘 <b>Помощь</b>\n\n"
        "<b>Команды:</b>\n"
        "/start - Перезапустить бота\n"
        "/role - Сменить роль (Заказчик/Водитель)\n"
        "/order - Создать новый заказ (для заказчиков)\n"
        "/orders - Список открытых заказов\n"
        "/me - Мой профиль и активный заказ\n"
        "/id - Узнать ID чата\n"
        "\n"
        "Если бот не отвечает, попробуйте написать /start снова."
    )


@router.message(Command("id"))
async def cmd_id(message: types.Message):
    await message.answer(f"ID этого чата: `{message.chat.id}`")


def register_start(dp):
    dp.include_router(router)
