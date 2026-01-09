from aiogram.fsm.state import State, StatesGroup
from enum import Enum, auto
from datetime import datetime
from typing import Optional


class OrderStatus(Enum):
    """Статусы заказа"""
    CREATED = auto()            # Заказ создан
    WAITING_DRIVER = auto()     # Ожидает водителя
    DRIVER_ASSIGNED = auto()    # Водитель назначен
    IN_PROGRESS = auto()        # В процессе выполнения
    COMPLETED = auto()          # Завершен
    CANCELLED = auto()          # Отменен
    EXPIRED = auto()            # Время на подтверждение истекло


class UserRole(Enum):
    """Роли пользователей"""
    CUSTOMER = "customer"
    DRIVER = "driver"


class OrderState(StatesGroup):
    """Состояния для процесса создания заказа"""
    waiting_for_cargo = State()      # Ожидание описания груза
    waiting_for_from = State()       # Ожидание адреса забора груза
    waiting_for_to = State()         # Ожидание адреса доставки
    waiting_for_phone = State()      # Ожидание номера телефона
    confirm_order = State()          # Подтверждение заказа


class DriverState(StatesGroup):
    """Состояния водителя"""
    waiting_for_orders = State()     # Ожидание заказов
    order_taken = State()            # Заказ взят (30 минут на подтверждение)
    in_delivery = State()            # В процессе доставки


class Order:
    """Класс для работы с заказом"""
    def __init__(
        self,
        order_id: int,
        customer_id: int,
        cargo: str,
        from_addr: str,
        to_addr: str,
        phone: str,
        status: OrderStatus = OrderStatus.CREATED,
        driver_id: Optional[int] = None,
        created_at: Optional[datetime] = None,
        reserved_until: Optional[datetime] = None
    ):
        self.order_id = order_id
        self.customer_id = customer_id
        self.cargo = cargo
        self.from_addr = from_addr
        self.to_addr = to_addr
        self.phone = phone
        self.status = status
        self.driver_id = driver_id
        self.created_at = created_at or datetime.now()
        self.reserved_until = reserved_until

    def is_expired(self) -> bool:
        """Проверяет, истекло ли время на подтверждение заказа"""
        if not self.reserved_until:
            return False
        return datetime.now() > self.reserved_until
