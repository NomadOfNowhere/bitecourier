"""Session-backed shopping cart.

The session only stores {item_id: quantity}. Names and prices are always looked up in
the catalog, so the cookie never decides what an order costs.
"""
from dataclasses import asdict, dataclass

from flask import session

from catalog import Catalog
from config import DELIVERY_FEE, MAX_QUANTITY_PER_ITEM

SESSION_KEY = "cart"


# --- Reading and writing the session ---------------------------------------

def get_cart() -> dict[str, int]:
    return dict(session.get(SESSION_KEY, {}))


def _save(cart: dict[str, int]) -> None:
    session[SESSION_KEY] = cart


def add_item(item_id: str, quantity: int = 1) -> None:
    cart = get_cart()
    cart[item_id] = min(cart.get(item_id, 0) + quantity, MAX_QUANTITY_PER_ITEM)
    _save(cart)


def set_quantity(item_id: str, quantity: int) -> None:
    """Set an exact quantity; zero or less removes the item."""
    cart = get_cart()
    if quantity <= 0:
        cart.pop(item_id, None)
    else:
        cart[item_id] = min(quantity, MAX_QUANTITY_PER_ITEM)
    _save(cart)


def clear() -> None:
    session.pop(SESSION_KEY, None)


def item_count() -> int:
    return sum(get_cart().values())


# --- Pricing ---------------------------------------------------------------

@dataclass(frozen=True)
class CartLine:
    item_id: str
    name: str
    restaurant_id: str
    restaurant_name: str
    image_filename: str
    unit_price: float
    quantity: int

    @property
    def line_total(self) -> float:
        return round(self.unit_price * self.quantity, 2)

    def to_dict(self) -> dict:
        """Snapshot stored in orders.cart_json, so old orders survive menu changes."""
        return {**asdict(self), "line_total": self.line_total}


@dataclass(frozen=True)
class CartSummary:
    lines: list[CartLine]
    subtotal: float
    delivery_fee: float
    total: float

    @property
    def is_empty(self) -> bool:
        return not self.lines

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self.lines)


def summarize(catalog: Catalog) -> CartSummary:
    lines = []
    for item_id, quantity in get_cart().items():
        item = catalog.item(item_id)
        if item is None:
            continue  # removed from items.json after it was added to the cart
        restaurant = catalog.restaurant(item["restaurant_id"])
        lines.append(CartLine(
            item_id=item_id,
            name=item["name"],
            restaurant_id=item["restaurant_id"],
            restaurant_name=restaurant["name"],
            image_filename=item["image_filename"],
            unit_price=item["price"],
            quantity=quantity,
        ))

    subtotal = round(sum(line.line_total for line in lines), 2)
    delivery_fee = DELIVERY_FEE if lines else 0.0
    return CartSummary(lines, subtotal, delivery_fee, round(subtotal + delivery_fee, 2))
