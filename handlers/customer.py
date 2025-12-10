import json
from aiogram import Router, types
from database import db

router = Router()


async def get_user_role(user_id: int) -> str | None:
    cur = await db.db.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    row = await cur.fetchone()
    return row[0] if row else None


async def get_session(chat_id: int):
    cur = await db.db.execute(
        "SELECT step, temp FROM sessions WHERE chat_id = ?", (chat_id,)
    )
    row = await cur.fetchone()
    if not row:
        return None
    step, temp_json = row
    temp = json.loads(temp_json) if temp_json else {}
    return {"step": step, "temp": temp}


async def save_session(chat_id: int, step: str, temp: dict):
    temp_json = json.dumps(temp, ensure_ascii=False)
    await db.db.execute(
        """
        INSERT INTO sessions (chat_id, step, temp)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET step = excluded.step, temp = excluded.temp
        """,
        (chat_id, step, temp_json),
    )
    await db.db.commit()


async def delete_session(chat_id: int):
    await db.db.execute("DELETE FROM sessions WHERE chat_id = ?", (chat_id,))
    await db.db.commit()


@router.message()
async def customer_flow(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # 1. Проверяем роль
    role = await get_user_role(user_id)
    if role != "customer":
        # не заказчик — сейчас не обрабатываем
        return

    text = (message.text or "").strip()
    if not text:
        return

    # 2. Загружаем сессию (если есть)
    session = await get_session(chat_id)

    # 2.1. Если нет сессии — начинаем новый заказ
    if session is None:
        # создаём сессию и спрашиваем про груз
        await save_session(chat_id, "ask_cargo", {})
        await message.answer("Начнём оформление заказа.\nЧто везём? Опишите груз:")
        return

    step = session["step"]
    temp = session["temp"]

    # 3. Обработка шагов
    if step == "ask_cargo":
        temp["cargo"] = text
        await save_session(chat_id, "ask_from", temp)
        await message.answer("Откуда забрать груз? Напишите адрес отправления:")
        return

    if step == "ask_from":
        temp["from_addr"] = text
        await save_session(chat_id, "ask_to", temp)
        await message.answer("Куда доставить груз? Напишите адрес доставки:")
        return

    if step == "ask_to":
        temp["to_addr"] = text
        await save_session(chat_id, "ask_phone", temp)
        await message.answer("Укажите контактный телефон для связи:")
        return

    if step == "ask_phone":
        temp["phone"] = text

        # 4. Сохраняем заказ в БД
        cargo = temp.get("cargo", "")
        from_addr = temp.get("from_addr", "")
        to_addr = temp.get("to_addr", "")
        phone = temp.get("phone", "")

        await db.db.execute(
            """
            INSERT INTO orders (customer_id, cargo, from_addr, to_addr, phone, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, cargo, from_addr, to_addr, phone, "open"),
        )
        await db.db.commit()
        await delete_session(chat_id)

        summary = (
            "Ваш заказ сохранён:\n\n"
            f"Груз: {cargo}\n"
            f"Откуда: {from_addr}\n"
            f"Куда: {to_addr}\n"
            f"Телефон: {phone}\n\n"
            "Спасибо! Заказ отправлен в список открытых."
        )
        await message.answer(summary)
        return

    # На всякий случай: если step неизвестен — очищаем сессию и начинаем заново
    await delete_session(chat_id)
    await message.answer("Что-то пошло не так, давайте начнём оформление заказа заново.\nЧто везём?")
    await save_session(chat_id, "ask_cargo", {})