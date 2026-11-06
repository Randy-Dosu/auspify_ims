"""SQL for the categories table."""

import sqlite3

from errors import ConflictError, NotFoundError


def _row_to_dict(row):
    return {"id": row["id"], "name": row["name"], "product_count": row["product_count"]}


# product_count tells the UI how many products use a category (handy before
# attempting a delete).
_SELECT = """
SELECT c.id, c.name, COUNT(p.id) AS product_count
FROM categories c
LEFT JOIN products p ON p.category_id = c.id
"""


def list_categories(conn):
    rows = conn.execute(_SELECT + " GROUP BY c.id ORDER BY c.name COLLATE NOCASE").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_category(conn, category_id):
    row = conn.execute(_SELECT + " WHERE c.id = ? GROUP BY c.id", (category_id,)).fetchone()
    return _row_to_dict(row) if row else None


def create_category(conn, name):
    try:
        cur = conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
    except sqlite3.IntegrityError as err:
        if "UNIQUE" in str(err):
            raise ConflictError("A category with this name already exists.",
                                details={"name": "Already exists."})
        raise
    return get_category(conn, cur.lastrowid)


def update_category(conn, category_id, name):
    if get_category(conn, category_id) is None:
        raise NotFoundError("Category not found.")
    try:
        conn.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))
    except sqlite3.IntegrityError as err:
        if "UNIQUE" in str(err):
            raise ConflictError("A category with this name already exists.",
                                details={"name": "Already exists."})
        raise
    return get_category(conn, category_id)


def delete_category(conn, category_id):
    category = get_category(conn, category_id)
    if category is None:
        raise NotFoundError("Category not found.")
    # Friendly check first; the FOREIGN KEY ... ON DELETE RESTRICT in the
    # schema would block this anyway, but with a less helpful message.
    if category["product_count"] > 0:
        raise ConflictError(
            f"Cannot delete category '{category['name']}': "
            f"{category['product_count']} product(s) still use it."
        )
    conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
