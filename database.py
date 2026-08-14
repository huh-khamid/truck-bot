import asyncpg
import logging
import json
from typing import Optional, Dict, Any, List, Tuple
from config import DATABASE_URL

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        try:
            # When deploying to render, sometimes SSL requires 'ssl=require' or similar in DSN
            # However asyncpg by default doesn't strictly check SSL unless asked, but we should be ready
            self.pool = await asyncpg.create_pool(self.dsn)

            async with self.pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        role TEXT NOT NULL,
                        phone TEXT,
                        car_model TEXT,
                        active_order INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        id SERIAL PRIMARY KEY,
                        customer_id BIGINT NOT NULL,
                        cargo TEXT NOT NULL,
                        from_addr TEXT NOT NULL,
                        to_addr TEXT NOT NULL,
                        phone TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'created',
                        driver_id BIGINT,
                        tg_chat_id TEXT,
                        tg_message_id BIGINT,
                        reserved_until BIGINT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (customer_id) REFERENCES users(user_id) ON DELETE CASCADE,
                        FOREIGN KEY (driver_id) REFERENCES users(user_id) ON DELETE SET NULL
                    );
                """)
                
                # Update users active_order foreign key safely in Postgres
                await conn.execute("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 
                            FROM information_schema.table_constraints 
                            WHERE constraint_name = 'fk_active_order'
                        ) THEN
                            ALTER TABLE users ADD CONSTRAINT fk_active_order 
                            FOREIGN KEY (active_order) REFERENCES orders(id) ON DELETE SET NULL;
                        END IF;
                    END $$;
                """)

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        chat_id BIGINT PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        step TEXT,
                        temp TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    );
                """)

                await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_driver ON orders(driver_id);")

            logger.info("Database connection established and tables are ready")
        except Exception as e:
            logger.error(f"Error connecting to database: {e}")
            raise

    async def close(self):
        if self.pool:
            await self.pool.close()
            logger.info("Database connection closed")

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
                if row:
                    return dict(row)
                return None
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
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO users (
                        user_id, username, first_name, last_name, 
                        role, phone, car_model, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = COALESCE(EXCLUDED.username, users.username),
                        first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                        last_name = COALESCE(EXCLUDED.last_name, users.last_name),
                        role = COALESCE(EXCLUDED.role, users.role),
                        phone = COALESCE(EXCLUDED.phone, users.phone),
                        car_model = COALESCE(EXCLUDED.car_model, users.car_model),
                        updated_at = CURRENT_TIMESTAMP
                """, user_id, username, first_name, last_name, role, phone, car_model)
                return True
        except Exception as e:
            logger.error(f"Error creating/updating user {user_id}: {e}")
            return False

    async def create_order(
        self,
        customer_id: int,
        cargo: str,
        from_addr: str,
        to_addr: str,
        phone: str
    ) -> Optional[int]:
        try:
            async with self.pool.acquire() as conn:
                order_id = await conn.fetchval("""
                    INSERT INTO orders (
                        customer_id, cargo, from_addr, to_addr, phone, 
                        status, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                """, customer_id, cargo, from_addr, to_addr, phone, 'created')
                return order_id
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return None

    async def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT o.*, 
                           c.username as customer_username,
                           c.phone as customer_phone,
                           d.username as driver_username
                    FROM orders o
                    LEFT JOIN users c ON o.customer_id = c.user_id
                    LEFT JOIN users d ON o.driver_id = d.user_id
                    WHERE o.id = $1
                """, order_id)
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Error getting order {order_id}: {e}")
            return None

    async def get_session(self, chat_id: int) -> Optional[Dict[str, Any]]:
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM sessions WHERE chat_id = $1", chat_id)
                if row:
                    session = dict(row)
                    if session.get('temp'):
                        session['temp'] = json.loads(session['temp'])
                    return session
                return None
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
        try:
            temp_json = json.dumps(temp) if temp else None
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO sessions (chat_id, user_id, step, temp, updated_at)
                    VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                    ON CONFLICT(chat_id) DO UPDATE SET
                        step = COALESCE(EXCLUDED.step, sessions.step),
                        temp = COALESCE(EXCLUDED.temp, sessions.temp),
                        updated_at = CURRENT_TIMESTAMP
                """, chat_id, user_id, step, temp_json)
                return True
        except Exception as e:
            logger.error(f"Error saving session for chat {chat_id}: {e}")
            return False

    async def delete_session(self, chat_id: int) -> bool:
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("DELETE FROM sessions WHERE chat_id = $1", chat_id)
                return True
        except Exception as e:
            logger.error(f"Error deleting session for chat {chat_id}: {e}")
            return False

    # ADMIN METHODS
    async def get_stats(self) -> Dict[str, int]:
        try:
            async with self.pool.acquire() as conn:
                users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
                customers_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE role = 'customer'")
                drivers_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE role = 'driver'")
                total_orders = await conn.fetchval("SELECT COUNT(*) FROM orders")
                active_orders = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status NOT IN ('completed', 'cancelled')")
                return {
                    "total_users": users_count,
                    "customers": customers_count,
                    "drivers": drivers_count,
                    "total_orders": total_orders,
                    "active_orders": active_orders
                }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}

    async def get_all_users(self) -> List[int]:
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("SELECT user_id FROM users")
                return [row['user_id'] for row in rows]
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []

db = Database(DATABASE_URL)

async def init_db():
    await db.connect()
    return db

async def close_db():
    await db.close()