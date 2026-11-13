"""Placing orders and reading them back."""
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from cart import CartSummary
from catalog import Catalog
from checkout_form import DeliveryDetails
from config import TIME_ZONE
from db import get_db

FALLBACK_ETA_MINUTES = (30, 45)  # used if a restaurant has since left the catalog
LOCAL_TIME = ZoneInfo(TIME_ZONE)


def _new_order_id() -> str:
    """Short, unguessable id such as BC-7F3A91C2."""
    return "BC-" + secrets.token_hex(4).upper()


def create_order(summary: CartSummary, details: DeliveryDetails, card: dict) -> str:
    """Insert the order and return its public order_id."""
    cart_json = json.dumps([line.to_dict() for line in summary.lines])
    # Stored in UTC so the value means the same on any server; shown in LOCAL_TIME.
    placed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db = get_db()

    for _attempt in range(5):
        order_id = _new_order_id()
        try:
            db.execute(
                """
                INSERT INTO orders
                    (order_id, cart_json, address, subtotal, delivery_fee, total, timestamp,
                     customer_name, phone, delivery_notes, card_brand, card_last4, card_expiry)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (order_id, cart_json, details.address, summary.subtotal,
                 summary.delivery_fee, summary.total, placed_at,
                 details.full_name, details.phone, details.notes,
                 card["brand"], card["last4"], card["expiry"]),
            )
            db.commit()
            return order_id
        except sqlite3.IntegrityError:
            continue  # order_id collision (astronomically rare): pick another
    raise RuntimeError("Could not generate a unique order id")


def get_order(order_id: str) -> dict | None:
    row = get_db().execute(
        "SELECT * FROM orders WHERE order_id = ?", (order_id,)
    ).fetchone()
    if row is None:
        return None
    order = dict(row)
    order["lines"] = json.loads(order["cart_json"])
    order["placed_at"] = datetime.fromisoformat(order["timestamp"]).astimezone(LOCAL_TIME)
    return order


@dataclass(frozen=True)
class DeliveryWindow:
    earliest: datetime
    latest: datetime
    min_minutes: int
    max_minutes: int


def delivery_window(order: dict, catalog: Catalog) -> DeliveryWindow:
    """Estimate arrival. The slowest kitchen in the order sets the window."""
    restaurant_ids = {line["restaurant_id"] for line in order["lines"]}
    restaurants = [r for r in map(catalog.restaurant, restaurant_ids) if r]
    min_minutes = max((r["eta_min"] for r in restaurants), default=FALLBACK_ETA_MINUTES[0])
    max_minutes = max((r["eta_max"] for r in restaurants), default=FALLBACK_ETA_MINUTES[1])
    placed_at = order["placed_at"]
    return DeliveryWindow(
        earliest=placed_at + timedelta(minutes=min_minutes),
        latest=placed_at + timedelta(minutes=max_minutes),
        min_minutes=min_minutes,
        max_minutes=max_minutes,
    )
