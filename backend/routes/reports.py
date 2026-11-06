"""
Reporting endpoints.

    GET /api/reports/summary
    GET /api/reports/low-stock                 (?format=csv for a download)
    GET /api/reports/valuation-by-category     (?format=csv)
    GET /api/reports/movements?from=YYYY-MM-DD&to=YYYY-MM-DD   (default: last 30 days)
    GET /api/reports/top-moving-products?from=&to=&limit=5
"""

import csv
import io
from datetime import date, timedelta

from flask import Blueprint, Response, jsonify, request

from database import get_db
from errors import ValidationError
from models import reports as model
from validation import FieldErrors, parse_int

bp = Blueprint("reports", __name__, url_prefix="/api/reports")

DEFAULT_RANGE_DAYS = 30
MAX_RANGE_DAYS = 366


def _parse_date_range():
    """
    Read ?from= and ?to= (YYYY-MM-DD). Defaults to the last 30 days.
    Rejects malformed dates, from > to and ranges longer than a year.
    """
    errors = FieldErrors()
    today = date.today()
    values = {}
    for name, default in (("to", today), ("from", None)):
        raw = request.args.get(name, "").strip()
        if not raw:
            values[name] = default
            continue
        try:
            values[name] = date.fromisoformat(raw)
        except ValueError:
            errors.add(name, "Use the format YYYY-MM-DD.")
    errors.raise_if_any()

    date_to = values["to"]
    date_from = values["from"] or date_to - timedelta(days=DEFAULT_RANGE_DAYS - 1)
    if date_from > date_to:
        raise ValidationError("Validation failed.", details={"from": "'from' must not be after 'to'."})
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise ValidationError("Validation failed.",
                              details={"from": f"Date range cannot exceed {MAX_RANGE_DAYS} days."})
    return date_from, date_to


def _csv_safe(value):
    """
    Neutralise spreadsheet formula injection.

    A cell starting with = + - @ (or tab/CR) is executed as a formula by
    Excel/LibreOffice. A product named "=HYPERLINK(...)" could therefore run
    code on a manager's laptop when they open the export. Prefixing such
    values with a single quote makes spreadsheets treat them as text.
    """
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _csv_response(filename, columns, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([_csv_safe(row.get(key)) for key, _ in columns])
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Make sure browsers never try to display this as HTML.
            "Content-Type": "text/csv; charset=utf-8",
        },
    )


def _wants_csv():
    fmt = request.args.get("format", "json").lower()
    if fmt not in ("json", "csv"):
        raise ValidationError("Validation failed.", details={"format": "Must be 'json' or 'csv'."})
    return fmt == "csv"


@bp.get("/summary")
def summary():
    return jsonify(model.summary(get_db()))


@bp.get("/low-stock")
def low_stock():
    items = model.low_stock(get_db())
    if _wants_csv():
        columns = [("sku", "SKU"), ("name", "Product"), ("category_name", "Category"),
                   ("supplier_name", "Supplier"), ("quantity_in_stock", "Quantity"),
                   ("reorder_level", "Reorder level"), ("shortfall", "Shortfall"),
                   ("unit_price", "Unit price"), ("stock_status", "Status")]
        return _csv_response(f"low-stock-{date.today().isoformat()}.csv", columns, items)
    return jsonify({"items": items, "total": len(items)})


@bp.get("/valuation-by-category")
def valuation_by_category():
    items = model.valuation_by_category(get_db())
    if _wants_csv():
        columns = [("category_name", "Category"), ("product_count", "Products"),
                   ("total_units", "Units"), ("total_value", "Value")]
        return _csv_response(f"valuation-by-category-{date.today().isoformat()}.csv", columns, items)
    total_value = round(sum(i["total_value"] for i in items), 2)
    return jsonify({"items": items, "total_value": total_value})


@bp.get("/movements")
def movements():
    date_from, date_to = _parse_date_range()
    return jsonify(model.movements(get_db(), date_from, date_to))


@bp.get("/top-moving-products")
def top_moving_products():
    date_from, date_to = _parse_date_range()
    errors = FieldErrors()
    limit = parse_int(request.args, "limit", errors, default=5, min_value=1, max_value=50)
    errors.raise_if_any()
    items = model.top_moving_products(get_db(), date_from, date_to, limit)
    return jsonify({"from": date_from.isoformat(), "to": date_to.isoformat(), "items": items})
