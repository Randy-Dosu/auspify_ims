"""
Stock movements: the only code allowed to change products.quantity_in_stock.

Every function here does two things inside ONE database transaction:
  1. update the product's quantity
  2. insert a stock_transactions row describing the change
If either part fails, both are rolled back, so the history always explains
the current quantity exactly.
"""

from database import transaction
from errors import APIError, NotFoundError
from models.products import get_product, get_product_or_404

TRANSACTION_SELECT = """
SELECT t.id, t.product_id, p.sku, p.name AS product_name,
       t.type, t.quantity, t.reason, t.note, t.created_at
FROM stock_transactions t
JOIN products p ON p.id = t.product_id
"""


class InsufficientStockError(APIError):
    """Requested OUT/negative adjustment is larger than what is in stock (400)."""

    status_code = 400


def row_to_transaction(row):
    return {
        "id": row["id"],
        "product_id": row["product_id"],
        "sku": row["sku"],
        "product_name": row["product_name"],
        "type": row["type"],
        "quantity": row["quantity"],
        "reason": row["reason"],
        "note": row["note"],
        "created_at": row["created_at"],
    }


def _record(conn, product_id, movement_type, quantity, reason, note):
    """Insert the audit row. Called only from inside a transaction."""
    cur = conn.execute(
        """
        INSERT INTO stock_transactions (product_id, type, quantity, reason, note)
        VALUES (?, ?, ?, ?, ?)
        """,
        (product_id, movement_type, quantity, reason, note),
    )
    return cur.lastrowid


def _touch(conn, product_id):
    conn.execute(
        "UPDATE products SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
        (product_id,),
    )


def stock_in(conn, product_id, quantity, reason=None, note=None):
    """Receive `quantity` units (quantity > 0, validated by the route)."""
    get_product_or_404(conn, product_id)
    with transaction(conn):
        conn.execute(
            "UPDATE products SET quantity_in_stock = quantity_in_stock + ? WHERE id = ?",
            (quantity, product_id),
        )
        _touch(conn, product_id)
        tx_id = _record(conn, product_id, "IN", quantity, reason or "Stock received", note)
    return _result(conn, product_id, tx_id)


def stock_out(conn, product_id, quantity, reason=None, note=None):
    """
    Remove `quantity` units. Stock can never go below zero.

    The UPDATE only matches when enough stock is available
    (`AND quantity_in_stock >= ?`). If it changes 0 rows we know the stock was
    insufficient at the exact moment of the update, even if another request
    withdrew units a millisecond earlier - no read-then-write race is possible.
    """
    product = get_product_or_404(conn, product_id)
    with transaction(conn):
        cur = conn.execute(
            """
            UPDATE products
               SET quantity_in_stock = quantity_in_stock - ?
             WHERE id = ? AND quantity_in_stock >= ?
            """,
            (quantity, product_id, quantity),
        )
        if cur.rowcount == 0:
            # Re-read inside the transaction for an accurate message.
            current = conn.execute(
                "SELECT quantity_in_stock FROM products WHERE id = ?", (product_id,)
            ).fetchone()[0]
            raise InsufficientStockError(
                f"Insufficient stock for {product['sku']}: requested {quantity}, "
                f"only {current} available.",
                details={"quantity": f"Only {current} available."},
            )
        _touch(conn, product_id)
        tx_id = _record(conn, product_id, "OUT", quantity, reason or "Sale", note)
    return _result(conn, product_id, tx_id)


def adjust_stock(conn, product_id, new_quantity=None, delta=None, reason=None, note=None):
    """
    Correct the stock level after a physical count.

    Either `new_quantity` (the counted amount) or `delta` (+/- change) is
    given; the route guarantees exactly one of them. The ADJUSTMENT row stores
    the signed difference so the history still sums up to the new quantity.
    """
    product = get_product_or_404(conn, product_id)
    with transaction(conn):
        current = conn.execute(
            "SELECT quantity_in_stock FROM products WHERE id = ?", (product_id,)
        ).fetchone()[0]
        change = delta if delta is not None else new_quantity - current
        if change == 0:
            raise APIError("Adjustment would not change the quantity.",
                           details={"quantity": "No change."})
        target = current + change
        if target < 0:
            raise InsufficientStockError(
                f"Adjustment of {change} would make stock negative for {product['sku']} "
                f"(current {current}).",
                details={"quantity": f"Current stock is {current}."},
            )
        conn.execute(
            "UPDATE products SET quantity_in_stock = ? WHERE id = ?", (target, product_id)
        )
        _touch(conn, product_id)
        tx_id = _record(conn, product_id, "ADJUSTMENT", change,
                        reason or "Stock count correction", note)
    return _result(conn, product_id, tx_id)


def _result(conn, product_id, tx_id):
    """Response payload: the movement that was recorded + the updated product."""
    row = conn.execute(TRANSACTION_SELECT + " WHERE t.id = ?", (tx_id,)).fetchone()
    return {"transaction": row_to_transaction(row), "product": get_product(conn, product_id)}


def list_transactions_for_product(conn, product_id, limit=100):
    if get_product(conn, product_id) is None:
        raise NotFoundError("Product not found.")
    rows = conn.execute(
        TRANSACTION_SELECT + " WHERE t.product_id = ? ORDER BY t.created_at DESC, t.id DESC LIMIT ?",
        (product_id, limit),
    ).fetchall()
    return [row_to_transaction(r) for r in rows]


def list_recent_transactions(conn, limit=50):
    """Most recent movements across all products (for the Stock Movements page)."""
    rows = conn.execute(
        TRANSACTION_SELECT + " ORDER BY t.created_at DESC, t.id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [row_to_transaction(r) for r in rows]
