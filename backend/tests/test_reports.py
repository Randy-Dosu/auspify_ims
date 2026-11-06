"""Report calculations are checked against values computed by hand in the test."""

import csv
import io
from datetime import date, timedelta

import pytest

import database
from tests.conftest import make_product


@pytest.fixture
def inventory(client, category, supplier):
    """
    A small, fully known inventory:

      sku     price   qty  reorder   status     value
      A-1     10.00    0     5       out          0.00
      A-2      2.50    4     5       low         10.00
      A-3    100.00   30     5       in_stock  3000.00
      B-1      0.99   10    10       low          9.90   (no category / supplier)
      ------------------------------------------------
      total                44                  3019.90
    """
    other_cat = client.post("/api/categories", json={"name": "Office"}).get_json()
    products = {
        "A-1": make_product(client, sku="A-1", name="Alpha", unit_price=10, quantity_in_stock=0, reorder_level=5,
                            category_id=category["id"], supplier_id=supplier["id"]),
        "A-2": make_product(client, sku="A-2", name="Beta", unit_price=2.5, quantity_in_stock=4, reorder_level=5,
                            category_id=category["id"], supplier_id=supplier["id"]),
        "A-3": make_product(client, sku="A-3", name="Gamma", unit_price=100, quantity_in_stock=30, reorder_level=5,
                            category_id=category["id"]),
        "B-1": make_product(client, sku="B-1", name="Delta", unit_price=0.99, quantity_in_stock=10, reorder_level=10),
    }
    return {"products": products, "office": other_cat}


def test_summary_matches_hand_calculation(client, inventory):
    summary = client.get("/api/reports/summary").get_json()
    assert summary == {
        "total_products": 4,
        "total_units": 44,
        "total_value": 3019.9,
        "low_stock_count": 2,       # A-2 (4 <= 5) and B-1 (10 <= 10)
        "out_of_stock_count": 1,    # A-1
        "total_categories": 2,
        "total_suppliers": 1,
        "total_transactions": 3,    # initial stock rows for A-2, A-3, B-1 (A-1 started at 0)
    }


def test_summary_total_value_matches_sum_of_products_in_database(app, client, inventory):
    """Cross-check against the raw table, independent of the report SQL."""
    with app.app_context():
        rows = database.get_db().execute("SELECT quantity_in_stock, unit_price FROM products").fetchall()
    expected = round(sum(r["quantity_in_stock"] * r["unit_price"] for r in rows), 2)
    assert client.get("/api/reports/summary").get_json()["total_value"] == expected == 3019.9


def test_empty_database_reports_zeros_not_errors(client):
    assert client.get("/api/reports/summary").get_json() == {
        "total_products": 0, "total_units": 0, "total_value": 0.0, "low_stock_count": 0,
        "out_of_stock_count": 0, "total_categories": 0, "total_suppliers": 0, "total_transactions": 0,
    }
    assert client.get("/api/reports/low-stock").get_json() == {"items": [], "total": 0}
    assert client.get("/api/reports/valuation-by-category").get_json() == {"items": [], "total_value": 0}
    movements = client.get("/api/reports/movements").get_json()
    assert len(movements["days"]) == 30 and movements["totals"]["transactions"] == 0
    assert client.get("/api/reports/top-moving-products").get_json()["items"] == []
    csv_response = client.get("/api/reports/low-stock?format=csv")
    assert csv_response.status_code == 200
    assert csv_response.data.decode().strip().count("\n") == 0  # header only


def test_low_stock_report_contents_and_order(client, inventory):
    body = client.get("/api/reports/low-stock").get_json()
    assert body["total"] == 3
    # Ordered by quantity ascending (most urgent first).
    assert [(i["sku"], i["quantity_in_stock"], i["shortfall"], i["stock_status"]) for i in body["items"]] == [
        ("A-1", 0, 5, "out"),
        ("A-2", 4, 1, "low"),
        ("B-1", 10, 0, "low"),
    ]
    assert body["items"][0]["supplier_name"] == "Accra Tech"


def test_valuation_by_category(client, inventory):
    body = client.get("/api/reports/valuation-by-category").get_json()
    rows = {(i["category_name"]): i for i in body["items"]}
    assert rows["Electronics"]["product_count"] == 3
    assert rows["Electronics"]["total_units"] == 34
    assert rows["Electronics"]["total_value"] == 3010.0
    assert rows["Uncategorised"]["product_count"] == 1
    assert rows["Uncategorised"]["total_value"] == 9.9
    assert "Office" not in rows or rows["Office"]["product_count"] == 0  # empty categories may be omitted
    assert body["total_value"] == 3019.9
    assert [i["total_value"] for i in body["items"]] == sorted((i["total_value"] for i in body["items"]), reverse=True)


def test_movements_buckets_today_correctly_and_fills_empty_days(client, inventory):
    pid = inventory["products"]["A-3"]["id"]
    client.post("/api/stock/in", json={"product_id": pid, "quantity": 7})
    client.post("/api/stock/out", json={"product_id": pid, "quantity": 2})
    client.post("/api/stock/out", json={"product_id": pid, "quantity": 1})
    client.post("/api/stock/adjust", json={"product_id": pid, "delta": -4})

    today = date.today()
    start = today - timedelta(days=2)
    body = client.get(f"/api/reports/movements?from={start}&to={today}").get_json()
    assert [d["day"] for d in body["days"]] == [(start + timedelta(days=i)).isoformat() for i in range(3)]
    today_row = body["days"][-1]
    # initial stock rows (4 + 30 + 10 = 44 IN) + 7 IN, 3 OUT, -4 adjustment
    assert today_row["stock_in"] == 44 + 7
    assert today_row["stock_out"] == 3
    assert today_row["adjustments"] == -4
    assert today_row["net"] == 51 - 3 - 4
    assert today_row["transactions"] == 3 + 4
    assert body["days"][0] == {"day": start.isoformat(), "stock_in": 0, "stock_out": 0, "adjustments": 0,
                               "transactions": 0, "net": 0}
    assert body["totals"] == {"stock_in": 51, "stock_out": 3, "adjustments": -4, "transactions": 7}


def test_movements_date_filter_excludes_other_days(app, client, inventory):
    """Back-date a transaction and confirm it only shows up in the matching range."""
    pid = inventory["products"]["A-3"]["id"]
    with app.app_context():
        database.get_db().execute(
            "INSERT INTO stock_transactions (product_id, type, quantity, reason, created_at) "
            "VALUES (?, 'OUT', 9, 'Sale', '2026-01-15T10:00:00Z')", (pid,))
    january = client.get("/api/reports/movements?from=2026-01-01&to=2026-01-31").get_json()
    assert january["totals"]["stock_out"] == 9 and january["totals"]["transactions"] == 1
    assert [d for d in january["days"] if d["transactions"]][0]["day"] == "2026-01-15"
    february = client.get("/api/reports/movements?from=2026-02-01&to=2026-02-28").get_json()
    assert february["totals"]["transactions"] == 0


@pytest.mark.parametrize("query", ["from=2026-13-01", "from=yesterday", "from=2026-02-10&to=2026-02-01",
                                   "from=2024-01-01&to=2026-01-01", "to=2026-01-01'; DROP TABLE products;--"])
def test_movements_rejects_bad_ranges(client, query):
    response = client.get(f"/api/reports/movements?{query}")
    assert response.status_code == 400
    assert response.get_json()["details"]


def test_top_moving_products(client, inventory):
    a3 = inventory["products"]["A-3"]["id"]
    b1 = inventory["products"]["B-1"]["id"]
    client.post("/api/stock/out", json={"product_id": a3, "quantity": 5})
    client.post("/api/stock/out", json={"product_id": a3, "quantity": 6})
    client.post("/api/stock/out", json={"product_id": b1, "quantity": 2})
    body = client.get("/api/reports/top-moving-products?limit=5").get_json()
    assert [(i["sku"], i["units_out"]) for i in body["items"]] == [("A-3", 11), ("B-1", 2)]
    assert body["items"][0]["units_in"] == 30  # initial stock counts as IN
    limited = client.get("/api/reports/top-moving-products?limit=1").get_json()
    assert len(limited["items"]) == 1
    assert client.get("/api/reports/top-moving-products?limit=0").status_code == 400
    assert client.get("/api/reports/top-moving-products?limit=51").status_code == 400


def test_csv_export_structure_and_formula_injection_guard(client, inventory):
    make_product(client, sku="EVIL-1", name='=HYPERLINK("http://evil.example","x")', unit_price=1, quantity_in_stock=0)
    make_product(client, sku="EVIL-2", name="+1+1", unit_price=1, quantity_in_stock=0)
    make_product(client, sku="EVIL-3", name="-cmd", unit_price=1, quantity_in_stock=0)
    make_product(client, sku="EVIL-4", name="@SUM(A1)", unit_price=1, quantity_in_stock=0)

    response = client.get("/api/reports/low-stock?format=csv")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.headers["Content-Disposition"].startswith('attachment; filename="low-stock-')
    assert response.headers["X-Content-Type-Options"] == "nosniff"

    rows = list(csv.reader(io.StringIO(response.data.decode("utf-8"))))
    assert rows[0] == ["SKU", "Product", "Category", "Supplier", "Quantity", "Reorder level", "Shortfall", "Unit price", "Status"]
    assert len(rows) == 1 + client.get("/api/reports/low-stock").get_json()["total"]
    names = {row[1] for row in rows[1:]}
    assert "'=HYPERLINK(\"http://evil.example\",\"x\")" in names
    assert "'+1+1" in names and "'-cmd" in names and "'@SUM(A1)" in names
    assert not any(n.startswith(("=", "+", "-", "@")) for n in names)
    # JSON keeps the raw value - escaping is only applied to the CSV.
    assert any(i["name"] == "+1+1" for i in client.get("/api/reports/low-stock").get_json()["items"])
    assert client.get("/api/reports/low-stock?format=pdf").status_code == 400
