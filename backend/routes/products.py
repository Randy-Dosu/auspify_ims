"""Product endpoints: /api/products"""

from flask import Blueprint, jsonify, request

from database import get_db
from models import products as model
from models import stock as stock_model
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


MAX_PER_PAGE = 100
STOCK_STATUSES = ("in_stock", "low", "out")


def _parse_list_params(args):
    """
    Validate the query string of GET /api/products.

    Every parameter is optional. Invalid values produce a 400 with a message
    per parameter rather than being silently ignored, so typos in a client are
    noticed immediately.
    """
    errors = FieldErrors()
    filters = {}

    search = parse_text(args, "search", errors, max_length=100)
    if search:
        filters["search"] = search
    filters["category_id"] = parse_int(args, "category", errors, min_value=1)
    filters["supplier_id"] = parse_int(args, "supplier", errors, min_value=1)

    status = (args.get("stock_status") or "").strip().lower()
    if status:
        if status in STOCK_STATUSES:
            filters["stock_status"] = status
        else:
            errors.add("stock_status", f"Must be one of: {', '.join(STOCK_STATUSES)}.")

    filters["min_price"] = parse_price(args, "min_price", errors)
    filters["max_price"] = parse_price(args, "max_price", errors)
    if (filters["min_price"] is not None and filters["max_price"] is not None
            and filters["min_price"] > filters["max_price"]):
        errors.add("min_price", "min_price cannot be greater than max_price.")

    sort = (args.get("sort") or "name").strip().lower()
    if sort not in model.SORT_COLUMNS:
        errors.add("sort", f"Must be one of: {', '.join(model.SORT_COLUMNS)}.")
    order = (args.get("order") or "asc").strip().lower()
    if order not in ("asc", "desc"):
        errors.add("order", "Must be 'asc' or 'desc'.")

    page = parse_int(args, "page", errors, default=1, min_value=1, max_value=1_000_000)
    per_page = parse_int(args, "per_page", errors, default=20, min_value=1, max_value=MAX_PER_PAGE)

    errors.raise_if_any()
    return filters, sort, order, page, per_page


@bp.get("")
def list_products():
    filters, sort, order, page, per_page = _parse_list_params(request.args)
    items, total = model.list_products(get_db(), filters, sort, order, page, per_page)
    total_pages = max(1, -(-total // per_page))  # ceiling division
    return jsonify({
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "sort": sort,
        "order": order,
    })


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


@bp.get("/<id:product_id>/transactions")
def product_transactions(product_id):
    """Movement history for one product, newest first."""
    errors = FieldErrors()
    limit = parse_int(request.args, "limit", errors, default=100, min_value=1, max_value=500)
    errors.raise_if_any()
    items = stock_model.list_transactions_for_product(get_db(), product_id, limit)
    return jsonify({"items": items})
