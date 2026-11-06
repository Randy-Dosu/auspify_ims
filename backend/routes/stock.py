"""
Stock movement endpoints.

    POST /api/stock/in       {product_id, quantity, reason?, note?}
    POST /api/stock/out      {product_id, quantity, reason?, note?}
    POST /api/stock/adjust   {product_id, new_quantity | delta, reason?, note?}
    GET  /api/stock/transactions?limit=50      recent movements, all products

(GET /api/products/<id>/transactions lives in routes/products.py.)
"""

from flask import Blueprint, jsonify, request

from database import get_db
from models import stock as model
from validation import (
    MAX_LONG_TEXT,
    MAX_QUANTITY,
    FieldErrors,
    get_json_body,
    parse_int,
    parse_text,
)

bp = Blueprint("stock", __name__, url_prefix="/api/stock")

MAX_REASON_LENGTH = 100


def _common_fields(data, errors):
    """Fields shared by every movement: which product, why, free-text note."""
    product_id = parse_int(data, "product_id", errors, required=True, min_value=1)
    reason = parse_text(data, "reason", errors, max_length=MAX_REASON_LENGTH)
    note = parse_text(data, "note", errors, max_length=MAX_LONG_TEXT)
    return product_id, reason, note


def _validate_movement(data):
    """IN / OUT share the same shape: a positive quantity."""
    errors = FieldErrors()
    product_id, reason, note = _common_fields(data, errors)
    quantity = parse_int(data, "quantity", errors, required=True, min_value=1, max_value=MAX_QUANTITY)
    errors.raise_if_any()
    return product_id, quantity, reason, note


@bp.post("/in")
def stock_in():
    product_id, quantity, reason, note = _validate_movement(get_json_body())
    return jsonify(model.stock_in(get_db(), product_id, quantity, reason, note)), 201


@bp.post("/out")
def stock_out():
    product_id, quantity, reason, note = _validate_movement(get_json_body())
    return jsonify(model.stock_out(get_db(), product_id, quantity, reason, note)), 201


@bp.post("/adjust")
def adjust_stock():
    data = get_json_body()
    errors = FieldErrors()
    product_id, reason, note = _common_fields(data, errors)
    new_quantity = parse_int(data, "new_quantity", errors, min_value=0, max_value=MAX_QUANTITY)
    delta = parse_int(data, "delta", errors, min_value=-MAX_QUANTITY, max_value=MAX_QUANTITY)

    has_new = "new_quantity" in data and data["new_quantity"] not in (None, "")
    has_delta = "delta" in data and data["delta"] not in (None, "")
    if has_new == has_delta:  # both or neither
        errors.add("new_quantity", "Provide exactly one of new_quantity or delta.")
    elif has_delta and delta == 0:
        errors.add("delta", "Delta cannot be zero.")
    errors.raise_if_any()

    result = model.adjust_stock(get_db(), product_id, new_quantity=new_quantity if has_new else None,
                                delta=delta if has_delta else None, reason=reason, note=note)
    return jsonify(result), 201


@bp.get("/transactions")
def recent_transactions():
    errors = FieldErrors()
    limit = parse_int(request.args, "limit", errors, default=50, min_value=1, max_value=500)
    errors.raise_if_any()
    return jsonify({"items": model.list_recent_transactions(get_db(), limit)})
