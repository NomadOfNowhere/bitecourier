"""Payment cards saved in the browser session.

Cards are added on the profile page and only selected at checkout, so the full
card number never reaches the order. Only brand, last4 and expiry are kept.
"""
import secrets

from flask import session

SESSION_KEY = "cards"
MAX_CARDS = 5


def get_cards() -> list[dict]:
    return list(session.get(SESSION_KEY, []))


def _save(saved: list[dict]) -> None:
    session[SESSION_KEY] = saved


def add_card(brand: str, last4: str, expiry: str) -> dict:
    card = {"id": secrets.token_hex(4), "brand": brand, "last4": last4, "expiry": expiry}
    _save((get_cards() + [card])[-MAX_CARDS:])
    return card


def get_card(card_id: str) -> dict | None:
    return next((c for c in get_cards() if c["id"] == card_id), None)


def remove_card(card_id: str) -> None:
    _save([c for c in get_cards() if c["id"] != card_id])
