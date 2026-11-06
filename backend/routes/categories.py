"""Category endpoints: /api/categories"""

from flask import Blueprint, jsonify

from database import get_db
from errors import NotFoundError
from models import categories as model
from validation import FieldErrors, get_json_body, parse_text

bp = Blueprint("categories", __name__, url_prefix="/api/categories")


def _validate(data):
    errors = FieldErrors()
    name = parse_text(data, "name", errors, required=True)
    errors.raise_if_any()
    return name


@bp.get("")
def list_categories():
    return jsonify({"items": model.list_categories(get_db())})


@bp.get("/<id:category_id>")
def get_category(category_id):
    category = model.get_category(get_db(), category_id)
    if category is None:
        raise NotFoundError("Category not found.")
    return jsonify(category)


@bp.post("")
def create_category():
    name = _validate(get_json_body())
    return jsonify(model.create_category(get_db(), name)), 201


@bp.put("/<id:category_id>")
def update_category(category_id):
    name = _validate(get_json_body())
    return jsonify(model.update_category(get_db(), category_id, name))


@bp.delete("/<id:category_id>")
def delete_category(category_id):
    model.delete_category(get_db(), category_id)
    return "", 204
