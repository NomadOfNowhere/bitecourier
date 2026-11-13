"""SQLite access: one connection per request, opened lazily and closed on teardown."""
import sqlite3
from contextlib import closing

from flask import Flask, current_app, g

# Columns added to `orders` after the first version. A data.db created before they
# existed gets them on the next start, so nobody has to delete their orders.
ADDED_COLUMNS = {
    "customer_name": "TEXT",
    "phone": "TEXT",
    "delivery_notes": "TEXT",
    "card_brand": "TEXT",
    "card_last4": "TEXT",
    "card_expiry": "TEXT",
}


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_error: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}
    for name, column_type in ADDED_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {name} {column_type}")
    conn.commit()


def init_app(app: Flask) -> None:
    """Create or upgrade the tables and register the teardown hook."""
    schema = app.config["SCHEMA_PATH"].read_text(encoding="utf-8")
    with closing(sqlite3.connect(app.config["DATABASE"])) as conn:
        conn.executescript(schema)
        _add_missing_columns(conn)
    app.teardown_appcontext(close_db)
