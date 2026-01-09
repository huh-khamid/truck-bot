import aiosqlite
import logging
import json
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

# Настройка логирования
logger = logging.getLogger(__name__)

class Database:
    def __init__(self, path: str = "db.sqlite"):
        self.path = path
        self.db = None

    async def connect(self):
        """Установить соединение с базой данных и инициализировать таблицы."""
        try:
            # Устанавливаем соединение с SQLite
            self.db = await aiosqlite.connect(self.path)

            # Включаем поддержку внешних ключей
            await self.db.execute("PRAGMA foreign_keys = ON")

            # Устанавливаем режим работы с датами
            await self.db.execute("PRAGMA journal_mode=WAL")

            # Создаем таблицу пользователей
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    role TEXT NOT NULL,
                    phone TEXT,
                    car_model TEXT,
                    active_order INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (active_order) REFERENCES orders(id) ON DELETE SET NULL
                );
            """)

            # Создаем таблицу заказов
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL,
                    cargo TEXT NOT NULL,
                    from_addr TEXT NOT NULL,
                    to_addr TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'created',
                    driver_id INTEGER,
                    tg_chat_id TEXT,
                    tg_message_id INTEGER,
                    reserved_until INTEGER,
                    created_at INTEGER DEFAULT (strftime('%s','now')),
                    updated_at INTEGER DEFAULT (strftime('%s','now')),
                    FOREIGN KEY (customer_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (driver_id) REFERENCES users(user_id) ON DELETE SET NULL
                );
            """)

            # Создаем таблицу сессий
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    chat_id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    step TEXT,
                    temp TEXT,  -- JSON данные
                    created_at INTEGER DEFAULT (strftime('%s','now')),
                    updated_at INTEGER DEFAULT (strftime('%s','now')),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)

            # Создаем индексы для ускорения запросов
            await self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            """)
            await self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
            """)
            await self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_driver ON orders(driver_id);
            """)

            await self.db.commit()
            logger.info("Database connection established and tables are ready")

        except Exception as e:
            logger.error(f"Error connecting to database: {e}")
            raise

    async def close(self):
        """Закрыть соединение с базой данных."""
        if self.db:
            await self.db.close()
            logger.info("Database connection closed")

    # ===== User Methods =====

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить данные пользователя по ID."""
        try:
            cursor = await self.db.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None

            return dict(zip([d[0] for d in cursor.description], row))
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    async def create_or_update_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        role: Optional[str] = None,
        phone: Optional[str] = None,
        car_model: Optional[str] = None
    ) -> bool:
        """Создать или обновить пользователя."""
        try:
            await self.db.execute("""
                INSERT INTO users (
                    user_id, username, first_name, last_name, 
                    role, phone, car_model, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    username = COALESCE(excluded.username, username),
                    first_name = COALESCE(excluded.first_name, first_name),
                    last_name = COALESCE(excluded.last_name, last_name),
                    role = COALESCE(excluded.role, role),
                    phone = COALESCE(excluded.phone, phone),
                    car_model = COALESCE(excluded.car_model, car_model),
                    updated_at = strftime('%s','now')
            """, (user_id, username, first_name, last_name, role, phone, car_model))

            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error creating/updating user {user_id}: {e}")
            await self.db.rollback()
            return False

    # ===== Order Methods =====

    async def create_order(
        self,
        customer_id: int,
        cargo: str,
        from_addr: str,
        to_addr: str,
        phone: str
    ) -> Optional[int]:
        """Создать новый заказ."""
        try:
            cursor = await self.db.execute("""
                INSERT INTO orders (
                    customer_id, cargo, from_addr, to_addr, phone, 
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
                RETURNING id
            """, (customer_id, cargo, from_addr, to_addr, phone, 'created'))

            order_id = (await cursor.fetchone())[0]
            await self.db.commit()
            return order_id
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            await self.db.rollback()
            return None

    async def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        """Получить заказ по ID."""
        try:
            cursor = await self.db.execute("""
                SELECT o.*, 
                       c.username as customer_username,
                       c.phone as customer_phone,
                       d.username as driver_username
                FROM orders o
                LEFT JOIN users c ON o.customer_id = c.user_id
                LEFT JOIN users d ON o.driver_id = d.user_id
                WHERE o.id = ?
            """, (order_id,))

            row = await cursor.fetchone()
            if not row:
                return None

            return dict(zip([d[0] for d in cursor.description], row))
        except Exception as e:
            logger.error(f"Error getting order {order_id}: {e}")
            return None

    # ===== Session Methods =====

    async def get_session(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Получить данные сессии по chat_id."""
        try:
            cursor = await self.db.execute(
                "SELECT * FROM sessions WHERE chat_id = ?",
                (chat_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None

            session = dict(zip([d[0] for d in cursor.description], row))
            if session.get('temp'):
                session['temp'] = json.loads(session['temp'])
            return session
        except Exception as e:
            logger.error(f"Error getting session for chat {chat_id}: {e}")
            return None

    async def save_session(
        self,
        chat_id: int,
        user_id: int,
        step: Optional[str] = None,
        temp: Optional[Dict] = None
    ) -> bool:
        """Сохранить данные сессии."""
        try:
            temp_json = json.dumps(temp) if temp else None
            await self.db.execute("""
                INSERT INTO sessions (chat_id, user_id, step, temp, updated_at)
                VALUES (?, ?, ?, ?, strftime('%s','now'))
                ON CONFLICT(chat_id) DO UPDATE SET
                    step = COALESCE(excluded.step, step),
                    temp = COALESCE(excluded.temp, temp),
                    updated_at = strftime('%s','now')
            """, (chat_id, user_id, step, temp_json))

            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving session for chat {chat_id}: {e}")
            await self.db.rollback()
            return False

    async def delete_session(self, chat_id: int) -> bool:
        """Удалить сессию."""
        try:
            await self.db.execute(
                "DELETE FROM sessions WHERE chat_id = ?",
                (chat_id,)
            )
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting session for chat {chat_id}: {e}")
            await self.db.rollback()
            return False

# Создаем глобальный экземпляр базы данных
db = Database()

async def init_db():
    """Инициализировать базу данных при запуске."""
    await db.connect()
    return db

async def close_db():
    """Закрыть соединение с базой данных при завершении работы."""
    await db.close()