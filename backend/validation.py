"""
Input validation helpers shared by all routes.

Principles:
  * Never trust the request. Every field is checked for type, length and range
    before it reaches SQL (which is always parameterised anyway).
  * Collect problems per field and raise ONE ValidationError with a `details`
    dict, so a form can highlight every invalid field at once.
"""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from flask import request

from errors import ValidationError

# Upper bounds keep payloads sane and protect against abuse.
MAX_SHORT_TEXT = 100       # names, SKUs, phone numbers
MAX_LONG_TEXT = 1000       # descriptions, notes
MAX_QUANTITY = 1_000_000_000
MAX_PRICE = Decimal("1000000000")
# Largest integer SQLite can store; anything bigger would crash the driver.
MAX_SQLITE_INT = 2**63 - 1

# A deliberately simple e-mail pattern: "something@something.something".
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Allow letters, digits, dash, underscore and dot in SKUs (e.g. "ELEC-001").
SKU_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def get_json_body():
    """
    Return the JSON object from the request or raise a 400.

    silent=True makes Flask return None (instead of raising) when the body is
    missing, not valid JSON or not sent as application/json.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError(
            "Request body must be a JSON object sent with Content-Type: application/json."
        )
    return data


class FieldErrors:
    """Small collector so we can report all invalid fields together."""

    def __init__(self):
        self.errors = {}

    def add(self, field, message):
        self.errors[field] = message

    def raise_if_any(self, message="Validation failed."):
        if self.errors:
            raise ValidationError(message, details=self.errors)


def parse_text(data, field, errors, *, required=False, max_length=MAX_SHORT_TEXT,
               pattern=None, pattern_message=None):
    """
    Read a string field. Returns the trimmed string, None when absent/blank
    (for optional fields) or the sentinel `errors` entry when invalid.
    """
    if field not in data or data[field] is None:
        if required:
            errors.add(field, "This field is required.")
        return None

    value = data[field]
    if not isinstance(value, str):
        errors.add(field, "Must be text.")
        return None

    value = value.strip()
    if not value:
        if required:
            errors.add(field, "This field is required.")
        return None
    if len(value) > max_length:
        errors.add(field, f"Must be at most {max_length} characters.")
        return None
    if "\x00" in value:
        errors.add(field, "Contains invalid characters.")
        return None
    if pattern and not pattern.match(value):
        errors.add(field, pattern_message or "Has an invalid format.")
        return None
    return value


def parse_int(data, field, errors, *, required=False, default=None,
              min_value=None, max_value=None):
    """
    Read an integer field. Accepts JSON numbers or digit strings ("12") because
    HTML inputs often send strings, but rejects booleans, decimals and junk.
    """
    if field not in data or data[field] is None or data[field] == "":
        if required:
            errors.add(field, "This field is required.")
        return default

    value = data[field]
    # bool is a subclass of int in Python - `true` must not become 1.
    if isinstance(value, bool):
        errors.add(field, "Must be a whole number.")
        return default
    if isinstance(value, float):
        if not value.is_integer():
            errors.add(field, "Must be a whole number.")
            return default
        value = int(value)
    elif isinstance(value, str):
        try:
            value = int(value.strip())
        except ValueError:
            errors.add(field, "Must be a whole number.")
            return default
    elif not isinstance(value, int):
        errors.add(field, "Must be a whole number.")
        return default

    if max_value is None:
        max_value = MAX_SQLITE_INT
    if min_value is not None and value < min_value:
        errors.add(field, f"Must be at least {min_value}.")
        return default
    if value > max_value:
        errors.add(field, f"Must be at most {max_value}.")
        return default
    return value


def parse_price(data, field, errors, *, required=False, default=None):
    """
    Read a money value and round it to 2 decimal places.

    We parse through Decimal (not float) so "19.99" is handled exactly, then
    return a float for storage in SQLite's REAL column.
    """
    if field not in data or data[field] is None or data[field] == "":
        if required:
            errors.add(field, "This field is required.")
        return default

    value = data[field]
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        errors.add(field, "Must be a number.")
        return default
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation:
        errors.add(field, "Must be a number.")
        return default
    if not amount.is_finite():
        errors.add(field, "Must be a number.")
        return default
    if amount < 0:
        errors.add(field, "Must be 0 or greater.")
        return default
    if amount > MAX_PRICE:
        errors.add(field, f"Must be at most {MAX_PRICE}.")
        return default
    # ROUND_HALF_UP is what people expect for money (12.345 -> 12.35); the
    # Decimal default would be banker's rounding (12.345 -> 12.34).
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def parse_email(data, field, errors):
    """Optional e-mail address with a basic format check."""
    value = parse_text(data, field, errors, max_length=254)
    if value is not None and not EMAIL_RE.match(value):
        errors.add(field, "Must be a valid e-mail address.")
        return None
    return value
