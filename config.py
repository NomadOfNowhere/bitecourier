"""App-wide settings. Every UPPERCASE name here is loaded into app.config."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Data files
DATABASE = BASE_DIR / "data.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
ITEMS_PATH = BASE_DIR / "items.json"
RESTAURANTS_PATH = BASE_DIR / "restaurants.json"
REVIEWS_PATH = BASE_DIR / "reviews.json"

# Server. Railway (and most hosts) hand the app a port in $PORT; 8080 is the local default.
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8080))

# Signs the session cookie (cart and the list of orders this browser may open).
# Anyone who knows the key can forge that cookie, so production needs its own secret:
#   export BITECOURIER_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
DEV_SECRET_KEY = "dev-only-not-secret"
SECRET_KEY = os.environ.get("BITECOURIER_SECRET_KEY", DEV_SECRET_KEY)
SESSION_COOKIE_SAMESITE = "Lax"

# Ordering rules
DELIVERY_FEE = 2.99
MAX_QUANTITY_PER_ITEM = 20

# Where we deliver. Checkout only accepts addresses in this city with one of these ZIP
# codes, and the notice at the top of every page uses `name`.
# The list is every ZIP code with street addresses in the city of San Francisco
# (PO-box-only codes and the airport's 94128 are left out). Trim it to your real coverage.
DELIVERY_AREA = {
    "name": "San Francisco",
    "city": "San Francisco",
    "state": "CA",
    "state_names": ("CA", "California"),
    "zip_codes": frozenset({
        "94102", "94103", "94104", "94105", "94107", "94108", "94109", "94110", "94111",
        "94112", "94114", "94115", "94116", "94117", "94118", "94121", "94122", "94123",
        "94124", "94127", "94129", "94130", "94131", "94132", "94133", "94134", "94158",
    }),
}

# Every time shown to customers (order placed, estimated arrival) is in this time zone,
# whatever the clock of the computer or cloud server running the app is set to.
TIME_ZONE = "America/Los_Angeles"

# How many of its own recent orders a browser may reopen (see app.order_confirmed)
MAX_REMEMBERED_ORDERS = 20
