# BiteCourier

A light-lunch delivery web app for San Francisco:
browse four restaurants, add dishes to a cart, enter your delivery details, place an
order and see a confirmation. Flask + SQLite on the server, plain HTML/CSS and a little
vanilla JS on the client, and Playwright to render the product-card and restaurant-cover
images from HTML templates.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium   # only needed for generate_images.py

python generate_images.py            # writes the PNGs under static/images/ (already included)
python app.py                        # http://localhost:8080
```

The server listens on `0.0.0.0:8080`, so other devices on your network can open it
too (e.g. your phone at `http://<your-computer-ip>:8080`).

For development with auto-reload (also reloads when `items.json` or
`restaurants.json` change):

```bash
FLASK_DEBUG=1 python app.py
```

Debug mode exposes Flask's interactive debugger, so only use it on a network you trust.

## Project layout

```
app.py                 Routes. Thin: parse the request, call a module, render.
config.py              Paths, port, delivery fee, limits.
catalog.py             Loads + validates items.json / restaurants.json; lookups.
cart.py                Session cart ({item_id: qty}) and price calculation.
checkout_form.py       The checkout fields: cleaning, validation, one-line address.
orders.py              Create/read orders, order ids, delivery-time estimate.
db.py                  One SQLite connection per request; creates/upgrades the table.
formatting.py          money(), clock(), time_range(); shared with the image script.
generate_images.py     Renders product cards and restaurant covers to PNG.

items.json             The menu (single source of truth: names, descriptions, prices, nutrition).
restaurants.json       Restaurant names, slugs, colors, cover image, delivery estimates.
schema.sql             The orders table.

templates/
  base.html            Header, flash messages, footer.
  _macros.html         Totals block, line-item list, checkout field, color variables.
  _icons.html          Logo mark and cart icon (inline SVG).
  index.html  restaurant.html  cart.html  checkout.html  order_confirmed.html  404.html
  image_templates/product_card.html      The 800x600 card design.
  image_templates/restaurant_cover.html  The 1200x600 cover design.
  image_templates/art/                   One illustration per item (<item_id>.svg).
static/
  css/style.css        Design tokens at the top in :root.
  js/app.js            Progressive enhancement (fetch for add-to-cart / place order).
  images/menu/         Generated product cards.
  images/restaurants/  Generated restaurant covers.
  images/favicon.svg   The logo mark.
```

## Routes

| Method | Path | What it does |
|---|---|---|
| GET | `/` | Landing page with the featured restaurants |
| GET | `/restaurant/<slug>` | Menu for one restaurant |
| POST | `/add-to-cart` | Adds `item_id` (optional `quantity`) to the session cart |
| POST | `/cart/update` | Sets a quantity from the cart page; `0` removes the item (extra route) |
| GET | `/cart` | Lines, quantities, subtotal, delivery fee, total, Checkout button |
| GET | `/checkout` | Form for name, phone and full delivery address, Place order button |
| POST | `/api/place-order` | Validates the details, inserts the order, clears the cart, returns the order id |
| GET | `/order-confirmed/<order_id>` | Items, total, delivery details and estimated delivery window |

`/add-to-cart` and `/api/place-order` accept a regular form post **or** JSON, and
answer the same way the caller asked:

- Browser form post (no JavaScript): redirect. Place order uses `303 See Other` to
  `/order-confirmed/<order_id>`.
- `Accept: application/json` or a JSON body: JSON. Place order returns
  `201 {"order_id": "BC-7F3A91C2", "redirect_url": "/order-confirmed/BC-7F3A91C2"}`
  and `app.js` follows `redirect_url`.

```bash
curl -c jar -b jar -H 'Accept: application/json' -d item_id=sak_01 localhost:8080/add-to-cart
curl -c jar -b jar -H 'Content-Type: application/json' localhost:8080/api/place-order -d '{
  "full_name": "Alex Rivera", "phone": "555 010 0199",
  "street": "123 Sample Street", "unit": "Apt 4B",
  "city": "San Francisco", "state": "CA", "postal_code": "94110",
  "notes": "Leave at the door"}'
```

### Checkout fields

| Field | Required | Rule |
|---|---|---|
| `full_name` | yes | at least a first and a last name |
| `phone` | yes | 7 to 15 digits; spaces, `+`, `-`, `.` and parentheses allowed |
| `street` | yes | street and number |
| `unit` | no | apartment, suite, floor |
| `city`, `state` | fixed | must be San Francisco, CA; filled in when left out |
| `postal_code` | yes | a 5-digit San Francisco ZIP code (`94110-1234` is accepted as `94110`) |
| `notes` | no | note for the courier, up to 200 characters |

The rules live in `checkout_form.py` and are applied on the server for both the form and
the JSON API. Invalid input returns `400`: as JSON,
`{"error": "Check the highlighted fields.", "fields": {"phone": "Enter a phone number with 7 to 15 digits."}}`,
which `app.js` shows under each field; without JavaScript, the form is rendered again
with what was typed and the same messages.

## Delivery area

BiteCourier delivers only within San Francisco, and the app says so in three places:

- A notice at the top of every page (`service-bar` in `base.html`).
- At checkout, the city and state are read-only and set to San Francisco, CA.
- The server rejects any ZIP code that isn't in the list, with a message such as
  "94601 is outside our delivery area. We only deliver within San Francisco."

Everything comes from `DELIVERY_AREA` in `config.py`: the name shown in notices, the
fixed city and state, and the set of accepted ZIP codes (every San Francisco ZIP with
street addresses). To cover a smaller zone, delete ZIP codes from that set; to move to
another city, change the whole block.

## How the pieces fit

- **Cart.** The session cookie only stores `{item_id: quantity}`. Prices and names are
  always read from `items.json` at render time, so the cookie can't change what an
  order costs. Quantities are capped at `MAX_QUANTITY_PER_ITEM`.
- **Orders.** `cart_json` stores a snapshot of each line (name, unit price, quantity,
  line total, restaurant), so old confirmations still render if the menu changes.
  `order_id` is random (`BC-` + 8 hex chars) so ids can't be guessed by counting.
  `address` holds the full address on one line; `customer_name`, `phone` and
  `delivery_notes` are extra columns. A `data.db` from before they existed is upgraded
  automatically on start (`db.ADDED_COLUMNS`).
- **Confirmation privacy.** The confirmation page shows a name, phone and address, so it
  only opens in the browser that placed the order (the order id is remembered in the
  session). Any other browser gets a 404, even with the right link.
- **Delivery estimate.** Each restaurant has `eta_min` / `eta_max` in
  `restaurants.json`. If a cart mixes restaurants, the slowest kitchen sets the window.
  The window is the order time plus those minutes; it is an estimate, not live tracking.
- **Time zone.** Order times are stored in UTC and always shown in San Francisco time
  (`TIME_ZONE` in `config.py`), whatever the clock of the machine running the app is set
  to. The time itself comes from that machine's clock, so keep it synced (cloud servers
  and normal laptops are, by default).
- **Delivery fee.** Flat `$2.99` (`DELIVERY_FEE` in `config.py`), charged only when the
  cart has items.

## Iterating on the product cards

1. Edit the tokens at the top of `templates/image_templates/product_card.html`
   (colors, font stacks, sizes in pt, cover height, padding).
2. Regenerate one card: `python generate_images.py --only sak_01`
3. Open `static/images/menu/sak_01.png`, repeat, then run without `--only`.

### Description and ingredients

Each item in `items.json` can have a `description` (one sentence) and an `ingredients`
list. The card's order is artwork, name and price, nutrition, then the description (up
to two lines) with the ingredients on one line below it; both texts are optional, and the description is also used in
the image's alt text. Text that doesn't fit ends in an ellipsis, and the script tells you:

```
wrote static/images/menu/sak_01.png  (illustration sak_01.svg)
  warning: text doesn't fit in: description. Shorten it in items.json or adjust the sizes in product_card.html.
```

About 170 characters fit in the description and about 100 in the ingredients line. To
make room for more, lower `--cover-height` or raise `--description-lines` in the template.

### Restaurant covers

Each restaurant's cover (`static/images/restaurants/<restaurant_id>.png`, 1200x600) is
rendered from `templates/image_templates/restaurant_cover.html`. It lays out the artwork
of the restaurant's first four dishes like a table seen from above; the first dish is the
large one in the middle. Move things with the `--w / --x / --y / --r` values in that
template, then `python generate_images.py --only sakura`. To use a photo instead, add
`art/<restaurant_id>.jpg` and it fills the whole cover.

`--only` takes an item id (one card) or a restaurant id (one cover). `--scale 2` renders
everything at double resolution for sharper images on hi-dpi screens (cards become
1600x1200; the page layout doesn't change).

### Artwork

The top half of each card shows a drawing of the dish from
`templates/image_templates/art/<item_id>.svg`. These are original flat, top-down
illustrations: plain SVG you can open in a browser, Figma or Inkscape and edit.

- **Use a real photo instead:** drop `art/<item_id>.jpg` (or `.png` / `.webp`) next to
  the SVG and regenerate. A photo always wins over the illustration. Use 4:3 photos you
  have the rights to; they are cropped to fill the 328×246 slot.
- **No artwork:** if neither file exists, the cover shows only the name, in a larger size.
- **New menu item:** add it to `items.json`, add `art/<item_id>.svg` (or a photo), then
  `python generate_images.py --only <item_id>`.
- **New restaurant:** add it to `restaurants.json` (with `"featured": true` to show it on
  the landing page) and its dishes to `items.json`, then run `python generate_images.py`.

The console shows which artwork each card used, e.g. `(illustration sak_01.svg)`.
Each SVG prefixes its internal ids with the item id (`sak01-maki`), so several can be
inlined on one page without clashing.

Restaurant cover colors (`cover_color`) and the cover text color (`accent_color`)
live in `restaurants.json`. The template is rendered with `StrictUndefined`, so a
misspelled variable fails loudly instead of rendering blank.

To use an installed Chrome instead of Playwright's Chromium:
`CHROMIUM_EXECUTABLE=/path/to/chrome python generate_images.py`

The cards use system serif fonts (Iowan Old Style / Palatino / Georgia), so they look
slightly different per OS. For identical output everywhere, add an `@font-face` with a
font file stored in the repo.

## Resetting

Delete `data.db` to clear all orders; it is recreated on the next start.

## Before deploying

The app runs end to end, but these are not done yet:

- **Secret key.** Set `BITECOURIER_SECRET_KEY` to a long random value. The app logs a
  warning at startup while it is using the built-in development key.
- **Production server.** `python app.py` starts Flask's development server. Use a WSGI
  server instead, e.g. `pip install gunicorn` then `gunicorn -b 0.0.0.0:8080 app:app`
  (on Windows: `waitress-serve --port=8080 app:app`), behind HTTPS, and never set
  `FLASK_DEBUG=1` there. With HTTPS in place, also set `SESSION_COOKIE_SECURE = True` in
  `config.py`.
- **Payment.** Checkout records the order and its total, but nothing charges the customer
  and the page doesn't say how they pay.
- **Sales tax and fees.** The total is subtotal + delivery fee; no sales tax is added.
- **Getting orders to the kitchen.** Orders are only written to `data.db`. Nothing
  notifies a restaurant or a courier.
- **Menu data.** Check every price, description, ingredient list and nutrition figure in
  `items.json` against the real dishes, since customers rely on them (allergies included).
- **Backups.** `data.db` holds names, phone numbers and addresses: back it up and keep it
  out of public folders and out of git (it is in `.gitignore`).

## Ideas for next steps

- CSRF tokens on the POST forms (e.g. Flask-WTF).
- Tests with `pytest` and Flask's test client.
- User accounts, so order history survives clearing cookies or switching devices.
- One-restaurant-per-cart rule, like most real delivery apps.
