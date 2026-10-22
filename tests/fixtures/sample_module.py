"""Учебный модуль складского учёта (фикстура для тестов code_ast)."""

import math
from dataclasses import dataclass

DEFAULT_VAT = 0.2
MAX_ITEMS = 1000


def add(a: int, b: int) -> int:
    return a + b


@dataclass
class Item:
    sku: str
    price: float
    quantity: int


class Warehouse:
    """Склад с остатками товаров."""

    def __init__(self, name: str) -> None:
        """Создаёт пустой склад."""
        self.name = name
        self.items: dict[str, Item] = {}

    def put(self, item: Item) -> None:
        """Кладёт товар на склад, увеличивая остаток, если SKU уже есть."""
        if item.sku in self.items:
            self.items[item.sku].quantity += item.quantity
        else:
            if len(self.items) >= MAX_ITEMS:
                raise ValueError(f'склад {self.name} переполнен')
            self.items[item.sku] = item

    def take(self, sku: str, quantity: int) -> Item:
        """Списывает товар со склада и возвращает списанную позицию."""
        item = self.items.get(sku)
        if item is None:
            raise KeyError(sku)
        if item.quantity < quantity:
            raise ValueError(f'недостаточно товара {sku}: {item.quantity} < {quantity}')
        item.quantity -= quantity
        return Item(sku=sku, price=item.price, quantity=quantity)

    def total_value(self, vat: float = DEFAULT_VAT) -> float:
        """Считает стоимость остатков с НДС."""
        net = sum(item.price * item.quantity for item in self.items.values())
        return round(net * (1 + vat), 2)


def calculate_penalty(amount: float, days_overdue: int, rate: float = 0.001) -> float:
    """Рассчитывает неустойку за просрочку поставки с учётом ограничений договора."""
    if amount <= 0:
        raise ValueError('сумма должна быть положительной')
    if days_overdue <= 0:
        return 0.0
    penalty = amount * rate * days_overdue
    # Неустойка ограничена 10% от стоимости товара (п. 5.2 договора).
    cap = amount * 0.1
    if penalty > cap:
        penalty = cap
    # Округляем вверх до копеек, как требует бухгалтерия.
    penalty = math.ceil(penalty * 100) / 100
    history = []
    for day in range(1, days_overdue + 1):
        accrued = min(amount * rate * day, cap)
        history.append((day, round(accrued, 2)))
    report_lines = [f'день {day}: {value} руб.' for day, value in history]
    summary = '\n'.join(report_lines)
    if len(summary) > 10_000:
        summary = summary[:10_000]
    return penalty
