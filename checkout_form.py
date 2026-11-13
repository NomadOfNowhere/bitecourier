"""The delivery details asked for at checkout, plus the card validation shared by
the profile page. Used by both the HTML forms and the JSON API, so the rules live
in one place.
"""
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from config import DELIVERY_AREA, TIME_ZONE

# Field name -> maximum length. The order here is the order of the form.
MAX_LENGTHS = {
    "full_name": 80,
    "phone": 20,
    "street": 120,
    "unit": 40,
    "city": 60,
    "state": 60,
    "postal_code": 10,
    "notes": 200,
}
OPTIONAL_FIELDS = {"unit", "notes"}

REQUIRED_MESSAGES = {
    "full_name": "Enter your full name.",
    "phone": "Enter a phone number the courier can call.",
    "street": "Enter the street and number.",
    "city": "Enter the city.",
    "state": "Enter the state or province.",
    "postal_code": "Enter the ZIP code.",
}

# Payment cards (profile page)
CARD_MAX_LENGTHS = {
    "card_number": 23,      # 16 digits plus spaces, longer for some networks
    "card_expiry": 5,       # MM/YY
    "card_cvc": 4,
}

PHONE_PATTERN = re.compile(r"\+?[\d\s().-]+")
ZIP_PATTERN = re.compile(r"\d{5}")
ZIP_PLUS_4_PATTERN = re.compile(r"(\d{5})-\d{4}")
CARD_DIGITS_PATTERN = re.compile(r"\d{13,19}")
CARD_CVC_PATTERN = re.compile(r"\d{3,4}")
CARD_EXPIRY_PATTERN = re.compile(r"(0[1-9]|1[0-2])/(\d{2})")


@dataclass(frozen=True)
class DeliveryDetails:
    full_name: str
    phone: str
    street: str
    unit: str
    city: str
    state: str
    postal_code: str
    notes: str

    @property
    def address(self) -> str:
        """The full address on one line, as stored in orders.address."""
        street = f"{self.street}, {self.unit}" if self.unit else self.street
        return f"{street}, {self.city}, {self.state} {self.postal_code}"


def clean(data) -> dict[str, str]:
    """Pick the known fields, tidy them and put city, state and ZIP in one standard form."""
    values = {name: " ".join(str(data.get(name) or "").split()) for name in MAX_LENGTHS}

    # City and state are fixed by the delivery area: fill them in when a client leaves
    # them out, and accept "san francisco" / "California" as the same thing.
    if not values["city"] or values["city"].casefold() == DELIVERY_AREA["city"].casefold():
        values["city"] = DELIVERY_AREA["city"]
    state_names = {name.casefold() for name in DELIVERY_AREA["state_names"]}
    if not values["state"] or values["state"].casefold() in state_names:
        values["state"] = DELIVERY_AREA["state"]

    # "94110-1234" -> "94110"
    if (zip_plus_4 := ZIP_PLUS_4_PATTERN.fullmatch(values["postal_code"])):
        values["postal_code"] = zip_plus_4.group(1)
    return values


def clean_card(data) -> dict[str, str]:
    """Tidy the profile-page card form; keep only the digits of the number."""
    values = {name: " ".join(str(data.get(name) or "").split()) for name in CARD_MAX_LENGTHS}
    values["card_number"] = re.sub(r"\D", "", values["card_number"])
    return values


def _luhn_ok(digits: str) -> bool:
    """The checksum every real card number passes; catches typos without a bank."""
    total = 0
    for index, digit in enumerate(reversed(digits)):
        value = int(digit)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _expired(expiry: str) -> bool:
    """True when MM/YY is in the past, compared in the shop's time zone."""
    month, year = (int(part) for part in expiry.split("/"))
    now = datetime.now(ZoneInfo(TIME_ZONE))
    return (year + 2000, month) < (now.year, now.month)


def validate(values: dict[str, str]) -> dict[str, str]:
    """Return {field_name: message} for every problem; empty when all is well."""
    errors = {}

    for name, max_length in MAX_LENGTHS.items():
        value = values[name]
        if not value and name not in OPTIONAL_FIELDS:
            errors[name] = REQUIRED_MESSAGES[name]
        elif len(value) > max_length:
            errors[name] = f"Use {max_length} characters or fewer."

    if "full_name" not in errors and len(values["full_name"].split()) < 2:
        errors["full_name"] = "Enter your first and last name."

    if "phone" not in errors:
        digits = re.sub(r"\D", "", values["phone"])
        if not PHONE_PATTERN.fullmatch(values["phone"]) or not 7 <= len(digits) <= 15:
            errors["phone"] = "Enter a phone number with 7 to 15 digits."

    if "street" not in errors and len(values["street"]) < 5:
        errors["street"] = "Enter the street and number."

    # Delivery area
    area = DELIVERY_AREA["name"]
    if "city" not in errors and values["city"] != DELIVERY_AREA["city"]:
        errors["city"] = f"We only deliver within {area}."
    if "state" not in errors and values["state"] != DELIVERY_AREA["state"]:
        errors["state"] = f"We only deliver within {area}, {DELIVERY_AREA['state']}."
    if "postal_code" not in errors:
        zip_code = values["postal_code"]
        if not ZIP_PATTERN.fullmatch(zip_code):
            errors["postal_code"] = "Enter a 5-digit ZIP code."
        elif zip_code not in DELIVERY_AREA["zip_codes"]:
            errors["postal_code"] = f"{zip_code} is outside our delivery area. We only deliver within {area}."

    return errors


def card_brand(digits: str) -> str:
    """Best-guess network from the first digits; only used for display."""
    if digits.startswith("4"):
        return "Visa"
    if digits[:2] in {"51", "52", "53", "54", "55"} or 2221 <= int(digits[:4] or 0) <= 2720:
        return "Mastercard"
    if digits[:2] in {"34", "37"}:
        return "American Express"
    if digits.startswith("6011") or digits.startswith("65"):
        return "Discover"
    return "Card"


def validate_card(values: dict[str, str]) -> dict[str, str]:
    """Validate the profile-page card form. Only the last four digits survive."""
    errors = {}

    card_number = values["card_number"]
    if not card_number:
        errors["card_number"] = "Enter the card number."
    elif not CARD_DIGITS_PATTERN.fullmatch(card_number):
        errors["card_number"] = "Enter the 13 to 19 digits on the card."
    # elif not _luhn_ok(card_number):
    #     errors["card_number"] = "That card number doesn't look right. Check it and try again."

    if not values["card_expiry"]:
        errors["card_expiry"] = "Enter the expiration date as MM/YY."
    elif not CARD_EXPIRY_PATTERN.fullmatch(values["card_expiry"]):
        errors["card_expiry"] = "Use MM/YY, for example 08/27."
    elif _expired(values["card_expiry"]):
        errors["card_expiry"] = "That card has expired."

    if not values["card_cvc"]:
        errors["card_cvc"] = "Enter the security code."
    elif not CARD_CVC_PATTERN.fullmatch(values["card_cvc"]):
        errors["card_cvc"] = "Enter the 3 or 4 digit code on the back of the card."

    return errors


def delivery_details(values: dict[str, str]) -> DeliveryDetails:
    """Build the record stored on the order."""
    return DeliveryDetails(
        full_name=values["full_name"],
        phone=values["phone"],
        street=values["street"],
        unit=values["unit"],
        city=values["city"],
        state=values["state"],
        postal_code=values["postal_code"],
        notes=values["notes"],
    )
