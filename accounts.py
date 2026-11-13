"""User accounts: sign up, log in and the per-user saved payment cards.

Cards belong to the logged-in user (stored in the cards table), not to the
browser session, so they follow the account across devices.
"""
import secrets
import sqlite3

from flask import session
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db

SESSION_KEY = "user_id"
MAX_CARDS = 5


# --- Session ---------------------------------------------------------------

def current_user() -> dict | None:
    """The logged-in user as {id, email, name}, or None."""
    user_id = session.get(SESSION_KEY)
    if user_id is None:
        return None
    row = get_db().execute(
        "SELECT id, email, name FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        session.pop(SESSION_KEY, None)
        return None
    return dict(row)


def log_out() -> None:
    session.pop(SESSION_KEY, None)


# --- Sign up and log in ------------------------------------------------------

def clean_credentials(data) -> dict[str, str]:
    values = {name: " ".join(str(data.get(name) or "").split()) for name in ("name", "email")}
    values["email"] = values["email"].casefold()
    values["password"] = str(data.get("password") or "")
    return values


def validate_signup(values: dict[str, str]) -> dict[str, str]:
    errors = {}
    if len(values["name"].split()) < 2:
        errors["name"] = "Enter your first and last name."
    if "@" not in values["email"] or "." not in values["email"].rsplit("@", 1)[-1]:
        errors["email"] = "Enter a valid email address."
    if len(values["password"]) < 8:
        errors["password"] = "Use at least 8 characters."
    if not errors and get_db().execute(
        "SELECT 1 FROM users WHERE email = ?", (values["email"],)
    ).fetchone():
        errors["email"] = "That email already has an account. Log in instead."
    return errors


def validate_login(values: dict[str, str]) -> dict[str, str]:
    errors = {}
    if not values["email"]:
        errors["email"] = "Enter your email."
    if not values["password"]:
        errors["password"] = "Enter your password."
    return errors


def create_user(values: dict[str, str]) -> dict:
    db = get_db()
    cursor = db.execute(
        "INSERT INTO users (email, name, password_hash, created_at) VALUES (?, ?, ?, datetime('now'))",
        (values["email"], values["name"], generate_password_hash(values["password"])),
    )
    db.commit()
    session[SESSION_KEY] = cursor.lastrowid
    return {"id": cursor.lastrowid, "email": values["email"], "name": values["name"]}


def authenticate(values: dict[str, str]) -> dict | None:
    """The user when email+password match, else None."""
    row = get_db().execute(
        "SELECT id, email, name, password_hash FROM users WHERE email = ?", (values["email"],)
    ).fetchone()
    if row is None or not check_password_hash(row["password_hash"], values["password"]):
        return None
    session[SESSION_KEY] = row["id"]
    return {"id": row["id"], "email": row["email"], "name": row["name"]}


# --- Cards -------------------------------------------------------------------

def get_cards(user_id: int) -> list[dict]:
    rows = get_db().execute(
        "SELECT id, brand, last4, expiry FROM cards WHERE user_id = ? ORDER BY rowid", (user_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def add_card(user_id: int, brand: str, last4: str, expiry: str) -> dict | None:
    """Save a card for the user; None when they already have MAX_CARDS."""
    if len(get_cards(user_id)) >= MAX_CARDS:
        return None
    card = {"id": secrets.token_hex(4), "brand": brand, "last4": last4, "expiry": expiry}
    db = get_db()
    try:
        db.execute(
            "INSERT INTO cards (id, user_id, brand, last4, expiry) VALUES (?, ?, ?, ?, ?)",
            (card["id"], user_id, brand, last4, expiry),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return None
    return card


def get_card(user_id: int, card_id: str) -> dict | None:
    """Only returns the card when it belongs to this user."""
    row = get_db().execute(
        "SELECT id, brand, last4, expiry FROM cards WHERE id = ? AND user_id = ?",
        (card_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def remove_card(user_id: int, card_id: str) -> None:
    db = get_db()
    db.execute("DELETE FROM cards WHERE id = ? AND user_id = ?", (card_id, user_id))
    db.commit()
