"""SQL for the products table."""

import sqlite3

from database import transaction
from errors import ConflictError, NotFoundError, ValidationError

# One SELECT reused by every read so the JSON shape is always identical.
# LEFT JOINs keep products whose category/supplier is not set.
PRODUCT_SELECT = """
SELECT p.id, p.sku, p.name, p.description,
       p.category_id, c.name AS category_name,
       p.supplier_id, s.name AS supplier_name,
       p.unit_price, p.quantity_in_stock, p.reorder_level,
       p.created_at, p.updated_at
FROM products p
LEFT JOIN categories c ON c.id = p.category_id
LEFT JOIN suppliers  s ON s.id = p.supplier_id
"""

# Columns a client is allowed to change through create/update.
# quantity_in_stock is deliberately NOT here for updates: it may only change
# through stock operations so that every movement is logged.
EDITABLE_FIELDS = ("sku", "name", "description", "category_id", "supplier_id",
                   "unit_price", "reorder_level")


def row_to_product(row):
    return {
        "id": row["id"],
        "sku": row["sku"],
        "name": row["name"],
        "description": row["description"],
        "category_id": row["category_id"],
        "category_name": row["category_name"],
        "supplier_id": row["supplier_id"],
        "supplier_name": row["supplier_name"],
        "unit_price": row["unit_price"],
        "quantity_in_stock": row["quantity_in_stock"],
        "reorder_level": row["reorder_level"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_products(conn):
    rows = conn.execute(PRODUCT_SELECT + " ORDER BY p.name COLLATE NOCASE, p.id").fetchall()
    return [row_to_product(r) for r in rows]


def get_product(conn, product_id):
    row = conn.execute(PRODUCT_SELECT + " WHERE p.id = ?", (product_id,)).fetchone()
    return row_to_product(row) if row else None


def get_product_or_404(conn, product_id):
    product = get_product(conn, product_id)
    if product is None:
        raise NotFoundError("Product not found.")
    return product


def _check_references(conn, data):
    """Give precise messages when category_id / supplier_id do not exist."""
    details = {}
    if data.get("category_id") is not None:
        if not conn.execute("SELECT 1 FROM categories WHERE id = ?", (data["category_id"],)).fetchone():
            details["category_id"] = "Category does not exist."
    if data.get("supplier_id") is not None:
        if not conn.execute("SELECT 1 FROM suppliers WHERE id = ?", (data["supplier_id"],)).fetchone():
            details["supplier_id"] = "Supplier does not exist."
    if details:
        raise ValidationError("Validation failed.", details=details)


def _raise_for_integrity(err):
    text = str(err)
    if "products.sku" in text:
        raise ConflictError("A product with this SKU already exists.",
                            details={"sku": "Already exists."})
    raise err


def create_product(conn, data):
    """
    Insert a product. If it starts with stock (quantity_in_stock > 0) we also
    write an IN transaction, so the audit trail explains where the units came
    from. Both inserts happen in ONE transaction.
    """
    _check_references(conn, data)
    initial_qty = data.get("quantity_in_stock") or 0
    try:
        with transaction(conn):
            cur = conn.execute(
                """
                INSERT INTO products
                    (sku, name, description, category_id, supplier_id,
                     unit_price, quantity_in_stock, reorder_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["sku"], data["name"], data.get("description"),
                 data.get("category_id"), data.get("supplier_id"),
                 data["unit_price"], initial_qty, data["reorder_level"]),
            )
            product_id = cur.lastrowid
            if initial_qty > 0:
                conn.execute(
                    """
                    INSERT INTO stock_transactions (product_id, type, quantity, reason)
                    VALUES (?, 'IN', ?, 'Initial stock')
                    """,
                    (product_id, initial_qty),
                )
    except sqlite3.IntegrityError as err:
        _raise_for_integrity(err)
    return get_product(conn, product_id)


def update_product(conn, product_id, data):
    """Update only the editable fields that were supplied."""
    get_product_or_404(conn, product_id)
    _check_references(conn, data)

    changes = {field: data[field] for field in EDITABLE_FIELDS if field in data}
    if not changes:
        raise ValidationError("No editable fields were provided.")

    # Column names come from our own whitelist (EDITABLE_FIELDS), never from
    # the client, so building the SET clause here is safe.
    set_clause = ", ".join(f"{column} = ?" for column in changes)
    params = list(changes.values()) + [product_id]
    try:
        conn.execute(
            f"UPDATE products SET {set_clause}, "
            f"updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
            params,
        )
    except sqlite3.IntegrityError as err:
        _raise_for_integrity(err)
    return get_product(conn, product_id)


def delete_product(conn, product_id):
    get_product_or_404(conn, product_id)
    # stock_transactions rows are removed by ON DELETE CASCADE.
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
