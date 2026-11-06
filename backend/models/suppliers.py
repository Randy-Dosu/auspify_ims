"""SQL for the suppliers table."""

from errors import ConflictError, NotFoundError


def _row_to_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "phone": row["phone"],
        "product_count": row["product_count"],
    }


_SELECT = """
SELECT s.id, s.name, s.email, s.phone, COUNT(p.id) AS product_count
FROM suppliers s
LEFT JOIN products p ON p.supplier_id = s.id
"""


def list_suppliers(conn):
    rows = conn.execute(_SELECT + " GROUP BY s.id ORDER BY s.name COLLATE NOCASE").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_supplier(conn, supplier_id):
    row = conn.execute(_SELECT + " WHERE s.id = ? GROUP BY s.id", (supplier_id,)).fetchone()
    return _row_to_dict(row) if row else None


def create_supplier(conn, name, email=None, phone=None):
    cur = conn.execute(
        "INSERT INTO suppliers (name, email, phone) VALUES (?, ?, ?)", (name, email, phone)
    )
    return get_supplier(conn, cur.lastrowid)


def update_supplier(conn, supplier_id, name, email=None, phone=None):
    if get_supplier(conn, supplier_id) is None:
        raise NotFoundError("Supplier not found.")
    conn.execute(
        "UPDATE suppliers SET name = ?, email = ?, phone = ? WHERE id = ?",
        (name, email, phone, supplier_id),
    )
    return get_supplier(conn, supplier_id)


def delete_supplier(conn, supplier_id):
    supplier = get_supplier(conn, supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found.")
    if supplier["product_count"] > 0:
        raise ConflictError(
            f"Cannot delete supplier '{supplier['name']}': "
            f"{supplier['product_count']} product(s) still use it."
        )
    conn.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
