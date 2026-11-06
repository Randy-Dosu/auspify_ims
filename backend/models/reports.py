"""
Reporting queries. Read-only; every number is computed by SQLite directly from
the products and stock_transactions tables, so reports can never drift from
the underlying data.
"""

from models.products import stock_status


def summary(conn):
    """Headline numbers for the dashboard cards. Works on an empty database."""
    row = conn.execute(
        """
        SELECT COUNT(*)                                          AS total_products,
               COALESCE(SUM(quantity_in_stock), 0)               AS total_units,
               ROUND(COALESCE(SUM(quantity_in_stock * unit_price), 0), 2) AS total_value,
               COALESCE(SUM(CASE WHEN quantity_in_stock > 0
                                  AND quantity_in_stock <= reorder_level THEN 1 ELSE 0 END), 0)
                                                                 AS low_stock_count,
               COALESCE(SUM(CASE WHEN quantity_in_stock = 0 THEN 1 ELSE 0 END), 0)
                                                                 AS out_of_stock_count
        FROM products
        """
    ).fetchone()
    counts = conn.execute(
        """
        SELECT (SELECT COUNT(*) FROM categories)         AS total_categories,
               (SELECT COUNT(*) FROM suppliers)          AS total_suppliers,
               (SELECT COUNT(*) FROM stock_transactions) AS total_transactions
        """
    ).fetchone()
    return {
        "total_products": row["total_products"],
        "total_units": row["total_units"],
        "total_value": row["total_value"],
        "low_stock_count": row["low_stock_count"],
        "out_of_stock_count": row["out_of_stock_count"],
        "total_categories": counts["total_categories"],
        "total_suppliers": counts["total_suppliers"],
        "total_transactions": counts["total_transactions"],
    }


def low_stock(conn):
    """
    Products that need attention: quantity <= reorder_level (this includes
    out-of-stock items). Most urgent first.
    """
    rows = conn.execute(
        """
        SELECT p.id, p.sku, p.name, c.name AS category_name, s.name AS supplier_name,
               p.quantity_in_stock, p.reorder_level, p.unit_price,
               (p.reorder_level - p.quantity_in_stock) AS shortfall
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        LEFT JOIN suppliers  s ON s.id = p.supplier_id
        WHERE p.quantity_in_stock <= p.reorder_level
        ORDER BY p.quantity_in_stock ASC, shortfall DESC, p.name COLLATE NOCASE
        """
    ).fetchall()
    return [
        {
            "id": r["id"],
            "sku": r["sku"],
            "name": r["name"],
            "category_name": r["category_name"],
            "supplier_name": r["supplier_name"],
            "quantity_in_stock": r["quantity_in_stock"],
            "reorder_level": r["reorder_level"],
            "unit_price": r["unit_price"],
            "shortfall": r["shortfall"],
            "stock_status": stock_status(r["quantity_in_stock"], r["reorder_level"]),
        }
        for r in rows
    ]


def valuation_by_category(conn):
    """Units and value (quantity x unit_price) grouped by category."""
    rows = conn.execute(
        """
        SELECT c.id AS category_id,
               COALESCE(c.name, 'Uncategorised') AS category_name,
               COUNT(p.id) AS product_count,
               COALESCE(SUM(p.quantity_in_stock), 0) AS total_units,
               ROUND(COALESCE(SUM(p.quantity_in_stock * p.unit_price), 0), 2) AS total_value
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        GROUP BY c.id
        ORDER BY total_value DESC, category_name COLLATE NOCASE
        """
    ).fetchall()
    return [dict(r) for r in rows]


def movements(conn, date_from, date_to):
    """
    Stock in vs out per day between two dates (inclusive, YYYY-MM-DD).
    Days with no activity are filled in with zeros so charts have a
    continuous x-axis.
    """
    rows = conn.execute(
        """
        SELECT date(created_at) AS day,
               SUM(CASE WHEN type = 'IN'  THEN quantity ELSE 0 END)        AS stock_in,
               SUM(CASE WHEN type = 'OUT' THEN quantity ELSE 0 END)        AS stock_out,
               SUM(CASE WHEN type = 'ADJUSTMENT' THEN quantity ELSE 0 END) AS adjustments,
               COUNT(*)                                                    AS transactions
        FROM stock_transactions
        WHERE date(created_at) BETWEEN ? AND ?
        GROUP BY day
        ORDER BY day
        """,
        (date_from.isoformat(), date_to.isoformat()),
    ).fetchall()
    by_day = {r["day"]: dict(r) for r in rows}

    series = []
    totals = {"stock_in": 0, "stock_out": 0, "adjustments": 0, "transactions": 0}
    day = date_from
    while day <= date_to:
        key = day.isoformat()
        entry = by_day.get(key, {"day": key, "stock_in": 0, "stock_out": 0,
                                 "adjustments": 0, "transactions": 0})
        entry["net"] = entry["stock_in"] - entry["stock_out"] + entry["adjustments"]
        series.append(entry)
        for field in totals:
            totals[field] += entry[field]
        day = day.fromordinal(day.toordinal() + 1)
    return {"from": date_from.isoformat(), "to": date_to.isoformat(),
            "days": series, "totals": totals}


def top_moving_products(conn, date_from, date_to, limit=5):
    """Products with the most units OUT (sold/used) in the period."""
    rows = conn.execute(
        """
        SELECT p.id, p.sku, p.name, c.name AS category_name,
               SUM(CASE WHEN t.type = 'OUT' THEN t.quantity ELSE 0 END) AS units_out,
               SUM(CASE WHEN t.type = 'IN'  THEN t.quantity ELSE 0 END) AS units_in,
               COUNT(t.id) AS transactions,
               p.quantity_in_stock
        FROM stock_transactions t
        JOIN products p ON p.id = t.product_id
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE date(t.created_at) BETWEEN ? AND ?
        GROUP BY p.id
        HAVING units_out > 0
        ORDER BY units_out DESC, transactions DESC, p.name COLLATE NOCASE
        LIMIT ?
        """,
        (date_from.isoformat(), date_to.isoformat(), limit),
    ).fetchall()
    return [dict(r) for r in rows]
