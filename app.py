"""BiteCourier: light-lunch delivery for San Francisco, built with Flask and SQLite.

Run:  python app.py        then open http://localhost:8080
Dev:  FLASK_DEBUG=1 python app.py   (auto-reload, also when items.json changes)
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import (
    Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for,
)

import cart
import cards
import checkout_form
import config
import db
import orders
from catalog import Catalog
from formatting import clock, money, time_range

app = Flask(__name__)
app.config.from_object(config)
app.add_template_filter(money)
app.add_template_filter(clock)
app.add_template_global(time_range)

catalog = Catalog.from_files(config.RESTAURANTS_PATH, config.ITEMS_PATH, config.REVIEWS_PATH)
db.init_app(app)

if app.config["SECRET_KEY"] == config.DEV_SECRET_KEY:
    app.logger.warning(
        "Using the built-in development SECRET_KEY. "
        "Set BITECOURIER_SECRET_KEY before putting this on the internet."
    )

ORDERS_SESSION_KEY = "orders"


# --- Helpers -----------------------------------------------------------------

def wants_json() -> bool:
    """True when the caller asked for JSON (our fetch() calls, or an API client)."""
    if request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["text/html", "application/json"])
    return best == "application/json"


def request_data():
    """Read a regular form post or a JSON object with the same code."""
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else request.form


def parse_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def current_summary() -> cart.CartSummary:
    return cart.summarize(catalog)


def render_checkout(summary: cart.CartSummary, values=None, errors=None):
    area = config.DELIVERY_AREA
    form = {
        # City and state are fixed by the delivery area and shown read-only.
        "entered": {"city": area["city"], "state": area["state"], **(values or {})},
        "errors": errors or {},
        "max_lengths": checkout_form.MAX_LENGTHS,
    }
    return render_template("checkout.html", summary=summary, form=form, cards=cards.get_cards())


def render_profile(values=None, errors=None):
    form = {
        "entered": values or {},
        "errors": errors or {},
        "max_lengths": checkout_form.CARD_MAX_LENGTHS,
    }
    return render_template("profile.html", form=form, cards=cards.get_cards())


def remember_order(order_id: str) -> None:
    """Note in the session that this browser placed the order."""
    recent = session.get(ORDERS_SESSION_KEY, [])
    session[ORDERS_SESSION_KEY] = (recent + [order_id])[-config.MAX_REMEMBERED_ORDERS:]


def placed_from_this_browser(order_id: str) -> bool:
    return order_id in session.get(ORDERS_SESSION_KEY, [])


@app.context_processor
def inject_globals():
    return {
        "cart_count": cart.item_count(),
        "delivery_area": config.DELIVERY_AREA,
        "current_year": datetime.now(ZoneInfo(config.TIME_ZONE)).year,
    }


# --- 1. Landing --------------------------------------------------------------

@app.get("/")
def index():
    restaurants = catalog.featured_restaurants()
    calorie_ranges = {r["restaurant_id"]: catalog.calorie_range(r["restaurant_id"]) for r in restaurants}
    return render_template(
        "index.html",
        restaurants=restaurants,
        calorie_ranges=calorie_ranges,
        reviews=catalog.featured_reviews(),
    )


# --- 2. Restaurant menu ------------------------------------------------------

@app.get("/restaurant/<slug>")
def restaurant(slug: str):
    found = catalog.restaurant_by_slug(slug)
    if found is None:
        abort(404)
    return render_template(
        "restaurant.html",
        restaurant=found,
        items=catalog.menu(found["restaurant_id"]),
        rating=catalog.restaurant_rating(found["restaurant_id"]),
    )


# --- 3. Add to cart ----------------------------------------------------------
@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    item_id = (request.form.get("item_id") or "").strip()
    item = catalog.item(item_id)
    if item is None:
        return jsonify({"error": "That dish is no longer available."}), 400

    # Diet-portion items ship as a pair unless the client overrides quantity.
    default_qty = item.get("default_quantity", 1)
    raw = request.form.get("quantity")
    try:
        quantity = max(1, int(raw)) if raw else default_qty
    except (TypeError, ValueError):
        quantity = default_qty

    cart.add_item(item_id, quantity)

    return jsonify({
        "name": item["name"],
        "cart_count": cart.item_count(),
        "redirect_url": request.referrer or url_for("index"),
    })


@app.post("/cart/update")
def update_cart():
    """Quantity stepper and Remove buttons on the cart page."""
    item_id = request.form.get("item_id", "")
    if catalog.item(item_id) is not None:
        cart.set_quantity(item_id, parse_int(request.form.get("quantity"), default=0))
    return redirect(url_for("view_cart"))


# --- 4. Cart -----------------------------------------------------------------

@app.get("/cart")
def view_cart():
    return render_template("cart.html", summary=current_summary())


# --- 5. Checkout -------------------------------------------------------------


# --- Profile: saved payment cards --------------------------------------------

@app.get("/profile")
def profile():
    return render_profile()


@app.post("/profile/add-card")
def add_card():
    values = checkout_form.clean_card(request_data())
    errors = checkout_form.validate_card(values)
    if errors:
        if wants_json():
            return jsonify(error="Check the highlighted fields.", fields=errors), 400
        return render_profile(values, errors), 400

    card = cards.add_card(
        brand=checkout_form.card_brand(values["card_number"]),
        last4=values["card_number"][-4:],
        expiry=values["card_expiry"],
    )

    if wants_json():
        return jsonify(**card), 201
    flash(f"Saved your {card['brand']} ending in {card['last4']}.", "success")
    return redirect(url_for("profile"))


@app.post("/profile/remove-card")
def remove_card():
    cards.remove_card(str(request_data().get("card_id", "")))
    if wants_json():
        return jsonify(cards=cards.get_cards())
    flash("Card removed.", "success")
    return redirect(url_for("profile"))


@app.get("/checkout")
def checkout():
    summary = current_summary()
    if summary.is_empty:
        flash("Your cart is empty. Add a dish before checking out.", "error")
        return redirect(url_for("view_cart"))
    return render_checkout(summary)


# --- 6. Place order ----------------------------------------------------------

@app.post("/api/place-order")
def place_order():
    summary = current_summary()
    if summary.is_empty:
        message = "Your cart is empty. Add a dish before placing an order."
        if wants_json():
            return jsonify(error=message), 400
        flash(message, "error")
        return redirect(url_for("view_cart"))

    values = checkout_form.clean(request_data())
    errors = checkout_form.validate(values)
    if errors:
        if wants_json():
            return jsonify(error="Check the highlighted fields.", fields=errors), 400
        # No JavaScript: show the form again with what was typed and what to fix.
        return render_checkout(summary, values, errors), 400

    card_id = str(request_data().get("card_id", ""))
    card = cards.get_card(card_id)
    if card is None:
        message = "Choose a payment card. Add one on your profile if the list is empty."
        if wants_json():
            return jsonify(error=message, fields={"card_id": message}), 400
        flash(message, "error")
        return redirect(url_for("checkout"))

    order_id = orders.create_order(summary, checkout_form.delivery_details(values), card)
    remember_order(order_id)
    cart.clear()
    redirect_url = url_for("order_confirmed", order_id=order_id)

    if wants_json():
        return jsonify(order_id=order_id, redirect_url=redirect_url), 201
    return redirect(redirect_url, code=303)


# --- 7. Confirmation ---------------------------------------------------------

@app.get("/order-confirmed/<order_id>")
def order_confirmed(order_id: str):
    # The page shows a name, phone and address, so only the browser that placed the
    # order may open it. Everyone else gets the same 404 as for an unknown id.
    order = orders.get_order(order_id) if placed_from_this_browser(order_id) else None
    if order is None:
        abort(404)
    return render_template(
        "order_confirmed.html",
        order=order,
        window=orders.delivery_window(order, catalog),
    )


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=os.environ.get("FLASK_DEBUG") == "1",
        extra_files=[str(config.ITEMS_PATH), str(config.RESTAURANTS_PATH)],
    )
