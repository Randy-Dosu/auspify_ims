"""Supplier endpoints: /api/suppliers"""

from flask import Blueprint, jsonify

from database import get_db
from errors import NotFoundError
from models import suppliers as model
from validation import FieldErrors, get_json_body, parse_email, parse_text

bp = Blueprint("suppliers", __name__, url_prefix="/api/suppliers")


def _validate(data):
    errors = FieldErrors()
    name = parse_text(data, "name", errors, required=True)
    email = parse_email(data, "email", errors)
    phone = parse_text(data, "phone", errors, max_length=30)
    errors.raise_if_any()
    return name, email, phone


@bp.get("")
def list_suppliers():
    return jsonify({"items": model.list_suppliers(get_db())})


@bp.get("/<id:supplier_id>")
def get_supplier(supplier_id):
    supplier = model.get_supplier(get_db(), supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found.")
    return jsonify(supplier)


@bp.post("")
def create_supplier():
    name, email, phone = _validate(get_json_body())
    return jsonify(model.create_supplier(get_db(), name, email, phone)), 201


@bp.put("/<id:supplier_id>")
def update_supplier(supplier_id):
    name, email, phone = _validate(get_json_body())
    return jsonify(model.update_supplier(get_db(), supplier_id, name, email, phone))


@bp.delete("/<id:supplier_id>")
def delete_supplier(supplier_id):
    model.delete_supplier(get_db(), supplier_id)
    return "", 204
