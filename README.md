# BiteCourier

A light-lunch delivery web app for San Francisco:
browse four restaurants, add dishes to a cart, create an account, save a card, enter your
delivery details, place an order and see the confirmation inline. Flask + SQLite on the
server, plain HTML/CSS and a little vanilla JS on the client, and Playwright to render the
product-card and restaurant-cover images from HTML templates.

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
accounts.py            Signup, login, sessions and per-user saved cards.
cart.py                Session cart ({item_id: qty}) and price calculation.
checkout_form.py       The checkout fields: cleaning, validation, one-line address.
orders.py              Create/read orders, order ids, delivery-time estimate.
db.py                  One SQLite connection per request; creates/upgrades the tables.
formatting.py          money(), clock(), time_range(); shared with the image script.
generate_images.py     Renders product cards and restaurant covers to PNG.

items.json             The menu (single source of truth: names, descriptions, prices, nutrition).
restaurants.json       Restaurant names, slugs, colors, cover image, delivery estimates.
schema.sql             The orders, users and cards tables.

templates/
  base.html            Header, flash messages, footer.
  _macros.html         Totals block, line-item list, checkout field, color variables.
  _icons.html          Logo mark and cart icon (inline SVG).
  index.html  restaurant.html  cart.html  checkout.html  order_confirmed.html  404.html
  login.html  profile.html
  _order_summary.html  _order_inline.html   Shared receipt (full page and inline)
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
| GET/POST | `/login` | Sign in |
| GET/POST | `/signup` | Create an account (name, email, password) |
| POST | `/logout` | Sign out |
| GET | `/profile` | The logged-in user's saved cards |
| POST | `/profile/add-card` | Save a card (brand, last four, expiry) |
| POST | `/profile/remove-card` | Remove one of the user's cards |
| GET | `/checkout` | Form for name, phone, full delivery address, note and saved card |
| POST | `/api/place-order` | Requires a logged-in user and a saved card; validates, inserts the order, clears the cart |
| GET | `/order-confirmed/<order_id>` | No-JS confirmation: items, total, delivery details and estimated delivery window |

`/add-to-cart` and `/api/place-order` accept a regular form post **or** JSON, and
answer the same way the caller asked:

- Browser form post (no JavaScript): redirect. Place order uses `303 See Other` to
  `/order-confirmed/<order_id>`.
- `Accept: application/json` or a JSON body: JSON. Place order returns
  `201 {"order_id": "BC-7F3A91C2", "redirect_url": "/order-confirmed/BC-7F3A91C2",
  "html": "<the rendered receipt>"}`. `app.js` inserts `html` below the Place order
  button and disables the form; it only follows `redirect_url` when no `html` is sent.

Place-order requires a logged-in user and one of that user's saved cards (`card_id`).
`/profile/add-card` returns the new card's `id` when asked for JSON:

```bash
curl -c jar -b jar -d 'name=Alex+Rivera&email=alex@example.com&password=correct-horse' \
  localhost:8080/signup
curl -c jar -b jar -H 'Accept: application/json' \
  -d 'card_number=4242424242424242&card_expiry=08/30&card_cvc=123' \
  localhost:8080/profile/add-card
curl -c jar -b jar -H 'Accept: application/json' -d item_id=sak_01 localhost:8080/add-to-cart
curl -c jar -b jar -H 'Content-Type: application/json' localhost:8080/api/place-order -d '{
  "full_name": "Alex Rivera", "phone": "555 010 0199",
  "street": "123 Sample Street", "unit": "Apt 4B",
  "city": "San Francisco", "state": "CA", "postal_code": "94110",
  "notes": "Leave at the door", "card_id": "<id from the add-card response>"}'
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
| `card_id` | yes | id of one of the logged-in user's saved cards (`/profile/add-card` returns it) |

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
- **Accounts and cards.** Signup/login stores users in `users`; saved cards live in
  `cards` (`id`, `brand`, `last4`, `expiry` — never the full number). Cards belong to
  the user, not to the browser session. Checkout requires a logged-in user and one of
  their saved cards.
- **Orders.** `cart_json` stores a snapshot of each line (name, unit price, quantity,
  line total, restaurant), so old confirmations still render if the menu changes.
  `order_id` is random (`BC-` + 8 hex chars) so ids can't be guessed by counting.
  `address` holds the full address on one line; `customer_name`, `phone`,
  `delivery_notes`, `card_brand`, `card_last4` and `card_expiry` are extra columns. A
  `data.db` from before they existed is upgraded automatically on start
  (`db.ADDED_COLUMNS`).
- **Inline confirmation.** With JavaScript, `/api/place-order` returns the rendered
  receipt in `html`; `app.js` shows it below the Place order button and disables the
  form. Without JavaScript, the `303` redirect to `/order-confirmed/<order_id>` renders
  the same receipt as a full page.
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

Delete `data.db` to clear all orders, users and cards; it is recreated on the next start.
On Railway the database lives on the container filesystem, so every deploy or restart
starts empty (see below).

## Deploying to Railway

The repo includes a `Procfile`:

```
web: gunicorn app:app --bind 0.0.0.0:$PORT
```

1. `railway login`
2. `railway init` in this directory, or connect the GitHub repo and set the service's
   root directory to `scenarios/bitecourier`.
3. `railway up` (or push to the connected branch).
4. In the service's **Variables**, set `BITECOURIER_SECRET_KEY` to a long random value:

   ```bash
   python -c 'import secrets; print(secrets.token_hex(32))'
   ```

   Do not set `PORT`; Railway injects it. Leave `FLASK_DEBUG` unset.
5. Generate a domain under **Settings → Networking**.

Railway detects Python from `requirements.txt` and installs Flask + gunicorn. `config.py`
reads `PORT` from the environment and the `Procfile` binds gunicorn to it. The app creates
and upgrades `data.db` on start (`db.init_app`).

`static/images/` is committed, so `generate_images.py` and Playwright are **not** needed at
build or runtime.

### SQLite persistence

`data.db` is on the container's ephemeral filesystem. Every deploy/restart recreates it
empty, which is the intended clean state for this scenario. If you need orders to survive:

- mount a Railway volume at a path such as `/data`;
- change `DATABASE` in `config.py` to read an environment variable (for example
  `BITECOURIER_DATA_DIR`) and point it at that path;
- do not mount the volume over `/app`, or it will shadow the application code.

### Cookies and HTTPS

Railway terminates TLS. The session cookie is `SameSite=Lax`; `SESSION_COOKIE_SECURE` is
not enabled by default. To require HTTPS-only cookies, set `SESSION_COOKIE_SECURE = True`
in `config.py` (or read it from an environment variable). Do not enable it for local HTTP
testing.

### Health check

There is no `/health` route; Railway's default TCP check is enough. If you add one, point
it at `/`.

### Production checklist

- [ ] `BITECOURIER_SECRET_KEY` set in Railway (the app logs a warning while using the
      built-in development key).
- [ ] `FLASK_DEBUG` not set to `1`.
- [ ] `SESSION_COOKIE_SECURE = True` if you want HTTPS-only cookies.
- [ ] `data.db` is not committed (it is in `.gitignore`).
- [ ] Mount a volume and point `DATABASE` at it if the database must survive redeploys.
- [ ] Payment is still simulated: the order records a saved card and its last four
      digits, but nothing charges the customer.
- [ ] No sales tax is added; the total is subtotal + delivery fee.
- [ ] Nothing notifies the kitchen or courier; orders only go to `data.db`.
- [ ] Menu data is checked against the real dishes (allergies included).

## Ideas for next steps

- CSRF tokens on the POST forms (e.g. Flask-WTF).
- Tests with `pytest` and Flask's test client.
- Order history per account (the `orders` table is not linked to `users` yet).
- One-restaurant-per-cart rule, like most real delivery apps.
