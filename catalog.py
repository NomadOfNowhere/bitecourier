"""Read-only catalog of restaurants, menu items and customer reviews.

items.json and restaurants.json are the single source of truth for names, prices and
nutrition. The Flask app and generate_images.py both read them through this class.
reviews.json holds the customer reviews shown on the landing and restaurant pages.
"""
import json
from pathlib import Path

ITEM_FIELDS = (
    "item_id", "restaurant_id", "name", "price",
    "calories", "protein_g", "carbs_g", "fat_g", "image_filename",
)
RESTAURANT_FIELDS = (
    "restaurant_id", "slug", "name", "description",
    "cover_color", "accent_color", "cover_image", "eta_min", "eta_max",
)
REVIEW_FIELDS = (
    "name", "neighborhood", "rating", "restaurant_id", "dish", "quote",
)


class Catalog:
    def __init__(self, restaurants: list[dict], items: list[dict], reviews: list[dict] | None = None):
        self.restaurants = restaurants
        self.items = items
        self.reviews = reviews or []
        self._restaurants_by_id = {r["restaurant_id"]: r for r in restaurants}
        self._restaurants_by_slug = {r["slug"]: r for r in restaurants}
        self._items_by_id = {i["item_id"]: i for i in items}
        self._reviews_by_restaurant: dict[str, list[dict]] = {}
        self._validate()

    @classmethod
    def from_files(cls, restaurants_path: Path, items_path: Path, reviews_path: Path | None = None) -> "Catalog":
        with open(restaurants_path, encoding="utf-8") as f:
            restaurants = json.load(f)
        with open(items_path, encoding="utf-8") as f:
            items = json.load(f)
        reviews = []
        if reviews_path is not None and reviews_path.exists():
            with open(reviews_path, encoding="utf-8") as f:
                reviews = json.load(f)
        return cls(restaurants, items, reviews)

    def _validate(self) -> None:
        """Fail at startup on a typo in the JSON, not later on a broken page."""
        for restaurant in self.restaurants:
            missing = [field for field in RESTAURANT_FIELDS if field not in restaurant]
            if missing:
                raise ValueError(
                    f"Restaurant {restaurant.get('restaurant_id', '?')} is missing: {', '.join(missing)}"
                )
        if len(self._restaurants_by_slug) != len(self.restaurants):
            raise ValueError("restaurants.json contains duplicate slug values")
        if len(self._items_by_id) != len(self.items):
            raise ValueError("items.json contains duplicate item_id values")
        for item in self.items:
            missing = [field for field in ITEM_FIELDS if field not in item]
            if missing:
                raise ValueError(f"Item {item.get('item_id', '?')} is missing: {', '.join(missing)}")
            if item["restaurant_id"] not in self._restaurants_by_id:
                raise ValueError(
                    f"Item {item['item_id']} points to unknown restaurant {item['restaurant_id']!r}"
                )
        for review in self.reviews:
            missing = [field for field in REVIEW_FIELDS if field not in review]
            if missing:
                raise ValueError(
                    f"Review by {review.get('name', '?')} is missing: {', '.join(missing)}"
                )
            if review["restaurant_id"] not in self._restaurants_by_id:
                raise ValueError(
                    f"Review by {review['name']} points to unknown restaurant {review['restaurant_id']!r}"
                )
            if not 1 <= review["rating"] <= 5:
                raise ValueError(f"Review by {review['name']} has a rating outside 1-5")
            self._reviews_by_restaurant.setdefault(review["restaurant_id"], []).append(review)

    # --- Lookups ------------------------------------------------------------

    def featured_restaurants(self) -> list[dict]:
        return [r for r in self.restaurants if r.get("featured")]

    def restaurant(self, restaurant_id: str) -> dict | None:
        return self._restaurants_by_id.get(restaurant_id)

    def restaurant_by_slug(self, slug: str) -> dict | None:
        return self._restaurants_by_slug.get(slug)

    def item(self, item_id: str) -> dict | None:
        return self._items_by_id.get(item_id)

    def menu(self, restaurant_id: str) -> list[dict]:
        return [i for i in self.items if i["restaurant_id"] == restaurant_id]

    def calorie_range(self, restaurant_id: str) -> tuple[int, int] | None:
        calories = [i["calories"] for i in self.menu(restaurant_id)]
        return (min(calories), max(calories)) if calories else None

    def featured_reviews(self) -> list[dict]:
        """The handful shown on the landing; ratings still count every review."""
        return [r for r in self.reviews if r.get("featured")]

    def restaurant_reviews(self, restaurant_id: str) -> list[dict]:
        return self._reviews_by_restaurant.get(restaurant_id, [])

    def restaurant_rating(self, restaurant_id: str) -> tuple[float, int] | None:
        """(average, review count) for a restaurant, or None if nobody reviewed it."""
        reviews = self.restaurant_reviews(restaurant_id)
        if not reviews:
            return None
        average = sum(r["rating"] for r in reviews) / len(reviews)
        return (round(average, 1), len(reviews))
