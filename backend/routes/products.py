"""Product endpoints: /api/products"""

from flask import Blueprint, jsonify

from database import get_db
from models import products as model
from validation import (
    MAX_LONG_TEXT,
    MAX_QUANTITY,
    SKU_RE,
    FieldErrors,
    get_json_body,
    parse_int,
    parse_price,
    parse_text,
)

bp = Blueprint("products", __name__, url_prefix="/api/products")


def _validate_product(data, *, partial=False):
    """
    Validate a product payload.

    partial=False (create): sku, name and unit_price are required and an
                            optional starting quantity_in_stock is accepted.
    partial=True  (update): only the fields present are validated/returned;
                            quantity_in_stock is rejected (use stock endpoints).
    """
    errors = FieldErrors()
    result = {}

    def want(field):
        # On update we only look at fields the client actually sent.
        return not partial or field in data

    if want("sku"):
        result["sku"] = parse_text(
            data, "sku", errors, required=True, max_length=50, pattern=SKU_RE,
            pattern_message="Use only letters, digits, dot, dash or underscore.",
        )
    if want("name"):
        result["name"] = parse_text(data, "name", errors, required=True)
    if want("description"):
        result["description"] = parse_text(data, "description", errors, max_length=MAX_LONG_TEXT)
    if want("category_id"):
        result["category_id"] = parse_int(data, "category_id", errors, min_value=1)
    if want("supplier_id"):
        result["supplier_id"] = parse_int(data, "supplier_id", errors, min_value=1)
    if want("unit_price"):
        result["unit_price"] = parse_price(data, "unit_price", errors, required=not partial)
    if want("reorder_level"):
        result["reorder_level"] = parse_int(
            data, "reorder_level", errors, default=10, min_value=0, max_value=MAX_QUANTITY
        )

    if partial:
        if "quantity_in_stock" in data:
            errors.add("quantity_in_stock",
                       "Quantity cannot be edited directly - record a stock movement instead.")
    else:
        result["quantity_in_stock"] = parse_int(
            data, "quantity_in_stock", errors, default=0, min_value=0, max_value=MAX_QUANTITY
        )

    errors.raise_if_any()
    return result


@bp.get("")
def list_products():
    items = model.list_products(get_db())
    return jsonify({"items": items, "total": len(items)})


@bp.get("/<id:product_id>")
def get_product(product_id):
    return jsonify(model.get_product_or_404(get_db(), product_id))


@bp.post("")
def create_product():
    data = _validate_product(get_json_body())
    return jsonify(model.create_product(get_db(), data)), 201


@bp.put("/<id:product_id>")
def update_product(product_id):
    data = _validate_product(get_json_body(), partial=True)
    return jsonify(model.update_product(get_db(), product_id, data))


@bp.delete("/<id:product_id>")
def delete_product(product_id):
    model.delete_product(get_db(), product_id)
    return "", 204
