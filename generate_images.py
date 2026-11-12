#!/usr/bin/env python3
"""Render the product-card and restaurant-cover PNGs with Playwright.

Usage:
    python generate_images.py                  # every card and every cover
    python generate_images.py --only sak_01    # one product card (an item_id)
    python generate_images.py --only sakura    # one restaurant cover (a restaurant_id)
    python generate_images.py --scale 2        # double resolution for hi-dpi screens

What it writes (existing PNGs are overwritten):
    static/images/menu/<image_filename>          800x600 card, from product_card.html
    static/images/restaurants/<cover_image>      1200x600 cover, from restaurant_cover.html

Artwork comes from templates/image_templates/art/:
    <item_id>.jpg / .jpeg / .png / .webp   a real photo (used first, if present)
    <item_id>.svg                          the illustration
    <restaurant_id>.jpg / ...              optional photo that fills the whole cover
A card with no artwork shows only the item name.

Set CHROMIUM_EXECUTABLE=/path/to/chrome to use an installed Chrome instead of
Playwright's bundled Chromium.
"""
import argparse
import base64
import os
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup
from playwright.sync_api import Page, sync_playwright

import config
from catalog import Catalog
from formatting import money

TEMPLATE_DIR = config.BASE_DIR / "templates" / "image_templates"
ART_DIR = TEMPLATE_DIR / "art"

CARD_TEMPLATE = "product_card.html"
CARD_DIR = config.BASE_DIR / "static" / "images" / "menu"
CARD_SIZE = (800, 600)

COVER_TEMPLATE = "restaurant_cover.html"
COVER_DIR = config.BASE_DIR / "static" / "images" / "restaurants"
COVER_SIZE = (1200, 600)
COVER_DISHES = 4

PHOTO_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", metavar="ID", help="an item_id (card) or a restaurant_id (cover)")
    parser.add_argument("--scale", type=int, choices=(1, 2, 3), default=1,
                        help="pixel density; 2 writes 1600x1200 cards (default: 1)")
    return parser.parse_args()


def build_jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,  # a typo in a template fails loudly
    )
    env.filters["money"] = money
    return env


# --- Artwork -------------------------------------------------------------------

def load_photo(stem: str) -> tuple[Markup | None, str]:
    for suffix, mime_type in PHOTO_TYPES.items():
        photo = ART_DIR / f"{stem}{suffix}"
        if photo.exists():
            # Inlined as a data URI so the page needs no file access or web server.
            data = base64.b64encode(photo.read_bytes()).decode("ascii")
            return Markup(f'<img src="data:{mime_type};base64,{data}" alt="">'), f"photo {photo.name}"
    return None, "no photo"


def load_art(item_id: str) -> tuple[Markup | None, str]:
    """Return (markup for a dish's artwork, a short label for the console)."""
    photo, label = load_photo(item_id)
    if photo is not None:
        return photo, label

    illustration = ART_DIR / f"{item_id}.svg"
    if illustration.exists():
        return Markup(illustration.read_text(encoding="utf-8")), f"illustration {illustration.name}"

    return None, "no artwork"


# --- Rendering -----------------------------------------------------------------

def render_card(env: Environment, item: dict, restaurant: dict) -> tuple[str, str]:
    art, label = load_art(item["item_id"])
    context = {
        "description": "",   # optional in items.json
        "ingredients": [],   # optional in items.json
        **item,
        "cover_color": restaurant["cover_color"],
        "accent_color": restaurant["accent_color"],
        "restaurant_name": restaurant["name"],
        "art": art,
    }
    return env.get_template(CARD_TEMPLATE).render(context), label


def render_cover(env: Environment, restaurant: dict, menu: list[dict]) -> tuple[str, str]:
    photo, label = load_photo(restaurant["restaurant_id"])
    dishes = [] if photo else [
        {"item_id": item["item_id"], "name": item["name"], "art": load_art(item["item_id"])[0]}
        for item in menu[:COVER_DISHES]
    ]
    if not photo:
        label = f"{sum(1 for dish in dishes if dish['art'])} dishes"
    html = env.get_template(COVER_TEMPLATE).render(
        restaurant_id=restaurant["restaurant_id"],
        name=restaurant["name"],
        cover_color=restaurant["cover_color"],
        accent_color=restaurant["accent_color"],
        dishes=dishes,
        photo=photo,
    )
    return html, label


# Runs in the page: names the card elements whose content is cut off or spills out.
FIND_CLIPPED_JS = """
() => [...document.querySelectorAll('.cover, .panel, .description, .ingredients')]
    .filter(el => el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)
    .map(el => el.classList[0])
"""


def screenshot(page: Page, html: str, size: tuple[int, int], output_path: Path) -> list[str]:
    """Save the PNG and return the names of any elements whose content doesn't fit."""
    width, height = size
    page.set_viewport_size({"width": width, "height": height})
    page.set_content(html, wait_until="load")
    page.evaluate("document.fonts.ready.then(() => true)")  # avoid fallback-font frames
    output_path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=output_path, clip={"x": 0, "y": 0, "width": width, "height": height})
    return page.evaluate(FIND_CLIPPED_JS)


def select_targets(catalog: Catalog, only: str | None) -> tuple[list[dict], list[dict]]:
    """Return (items whose cards to render, restaurants whose covers to render)."""
    if only is None:
        return catalog.items, catalog.restaurants
    if (item := catalog.item(only)) is not None:
        return [item], []
    if (restaurant := catalog.restaurant(only)) is not None:
        return [], [restaurant]
    item_ids = ", ".join(i["item_id"] for i in catalog.items)
    restaurant_ids = ", ".join(r["restaurant_id"] for r in catalog.restaurants)
    sys.exit(f"Unknown id {only!r}.\n  Items: {item_ids}\n  Restaurants: {restaurant_ids}")


def main() -> None:
    args = parse_args()
    catalog = Catalog.from_files(config.RESTAURANTS_PATH, config.ITEMS_PATH)
    items, restaurants = select_targets(catalog, args.only)
    env = build_jinja_env()

    executable = os.environ.get("CHROMIUM_EXECUTABLE") or None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable)
        page = browser.new_page(device_scale_factor=args.scale)

        for item in items:
            html, label = render_card(env, item, catalog.restaurant(item["restaurant_id"]))
            output_path = CARD_DIR / item["image_filename"]
            clipped = screenshot(page, html, CARD_SIZE, output_path)
            print(f"wrote {output_path.relative_to(config.BASE_DIR)}  ({label})")
            if clipped:
                print(f"  warning: text doesn't fit in: {', '.join(clipped)}. "
                      f"Shorten it in items.json or adjust the sizes in {CARD_TEMPLATE}.")

        for restaurant in restaurants:
            html, label = render_cover(env, restaurant, catalog.menu(restaurant["restaurant_id"]))
            output_path = COVER_DIR / restaurant["cover_image"]
            screenshot(page, html, COVER_SIZE, output_path)
            print(f"wrote {output_path.relative_to(config.BASE_DIR)}  ({label})")

        browser.close()

    print(f"Done: {len(items)} card(s), {len(restaurants)} cover(s).")


if __name__ == "__main__":
    main()
