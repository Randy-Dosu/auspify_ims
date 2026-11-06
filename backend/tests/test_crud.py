"""CRUD + validation tests for products, categories and suppliers."""

import pytest

from tests.conftest import make_product


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #


def test_create_product_returns_201_with_joined_names(client, category, supplier):
    product = make_product(client, category_id=category["id"], supplier_id=supplier["id"],
                           unit_price="19.99", quantity_in_stock=3)
    assert product["sku"] == "TEST-001"
    assert product["unit_price"] == 19.99
    assert product["quantity_in_stock"] == 3
    assert product["category_name"] == "Electronics"
    assert product["supplier_name"] == "Accra Tech"
    assert product["stock_status"] == "low"  # 3 <= reorder level 5


def test_initial_quantity_is_recorded_as_an_in_transaction(client):
    product = make_product(client, quantity_in_stock=7)
    history = client.get(f"/api/products/{product['id']}/transactions").get_json()["items"]
    assert [(t["type"], t["quantity"], t["reason"]) for t in history] == [("IN", 7, "Initial stock")]


def test_zero_initial_quantity_records_no_transaction(client):
    product = make_product(client, quantity_in_stock=0)
    history = client.get(f"/api/products/{product['id']}/transactions").get_json()["items"]
    assert history == []


@pytest.mark.parametrize("sku", ["TEST-001", "test-001", "TEST-001 "])
def test_duplicate_sku_is_rejected_case_insensitively(client, sku):
    make_product(client, sku="TEST-001")
    response = client.post("/api/products", json={"sku": sku, "name": "Dup", "unit_price": 1})
    assert response.status_code == 409
    assert response.get_json()["details"] == {"sku": "Already exists."}


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit_price", -1),
        ("unit_price", -0.01),
        ("unit_price", "abc"),
        ("unit_price", True),
        ("unit_price", "NaN"),
        ("unit_price", "Infinity"),
        ("quantity_in_stock", -5),
        ("quantity_in_stock", 1.5),
        ("quantity_in_stock", "many"),
        ("reorder_level", -1),
        ("name", ""),
        ("name", "   "),
        ("name", ["list"]),
        ("name", "x" * 101),
        ("sku", "has spaces"),
        ("sku", "x" * 51),
        ("description", "d" * 1001),
        ("category_id", 0),
        ("category_id", "1 OR 1=1"),
        ("category_id", 999999),
        ("supplier_id", 999999),
    ],
)
def test_invalid_product_fields_return_400_naming_the_field(client, field, value):
    payload = {"sku": "VALID-1", "name": "Valid", "unit_price": 1, field: value}
    response = client.post("/api/products", json=payload)
    assert response.status_code == 400, response.get_json()
    assert field in response.get_json()["details"]
    # Nothing was written.
    assert client.get("/api/products").get_json()["total"] == 0


def test_missing_required_fields_are_all_reported_at_once(client):
    response = client.post("/api/products", json={})
    assert response.status_code == 400
    assert set(response.get_json()["details"]) >= {"sku", "name", "unit_price"}


@pytest.mark.parametrize("price,expected", [("12.345", 12.35), ("12.344", 12.34), (0, 0.0), ("0.005", 0.01), (1e6, 1000000.0)])
def test_prices_are_rounded_half_up_to_two_decimals(client, price, expected):
    product = make_product(client, unit_price=price)
    assert product["unit_price"] == expected


def test_large_quantities_are_supported_up_to_the_cap(client):
    product = make_product(client, quantity_in_stock=1_000_000_000)
    assert product["quantity_in_stock"] == 1_000_000_000
    too_big = client.post("/api/products", json={"sku": "BIG-2", "name": "x", "unit_price": 1,
                                                 "quantity_in_stock": 1_000_000_001})
    assert too_big.status_code == 400


def test_update_product_changes_only_supplied_fields(client, product):
    response = client.put(f"/api/products/{product['id']}", json={"name": "Renamed", "unit_price": 99})
    assert response.status_code == 200
    updated = response.get_json()
    assert updated["name"] == "Renamed"
    assert updated["unit_price"] == 99.0
    assert updated["sku"] == product["sku"]
    assert updated["quantity_in_stock"] == 20
    assert updated["updated_at"] >= product["updated_at"]


def test_update_cannot_change_quantity_directly(client, product):
    response = client.put(f"/api/products/{product['id']}", json={"quantity_in_stock": 999})
    assert response.status_code == 400
    assert "quantity_in_stock" in response.get_json()["details"]
    assert client.get(f"/api/products/{product['id']}").get_json()["quantity_in_stock"] == 20


def test_update_with_no_editable_fields_is_rejected(client, product):
    response = client.put(f"/api/products/{product['id']}", json={"bogus": 1})
    assert response.status_code == 400


def test_update_to_existing_sku_conflicts(client, product):
    make_product(client, sku="OTHER-1")
    response = client.put(f"/api/products/{product['id']}", json={"sku": "other-1"})
    assert response.status_code == 409


def test_delete_product_removes_it_and_its_history(client, app, product):
    client.post("/api/stock/out", json={"product_id": product["id"], "quantity": 2})
    assert client.delete(f"/api/products/{product['id']}").status_code == 204
    assert client.get(f"/api/products/{product['id']}").status_code == 404
    assert client.delete(f"/api/products/{product['id']}").status_code == 404
    # ON DELETE CASCADE removed the transactions (no orphans).
    import database
    with app.app_context():
        count = database.get_db().execute(
            "SELECT COUNT(*) FROM stock_transactions WHERE product_id = ?", (product["id"],)
        ).fetchone()[0]
    assert count == 0


def test_unknown_product_ids_return_404(client):
    assert client.get("/api/products/12345").status_code == 404
    assert client.get("/api/products/0").status_code == 404
    assert client.get("/api/products/-1").status_code == 404
    assert client.get("/api/products/abc").status_code == 404
    assert client.get("/api/products/99999999999999999999").status_code == 404
    assert client.put("/api/products/12345", json={"name": "x"}).status_code == 404


# --------------------------------------------------------------------------- #
# Categories & suppliers
# --------------------------------------------------------------------------- #


def test_category_crud_cycle(client):
    created = client.post("/api/categories", json={"name": "  Office  "}).get_json()
    assert created["name"] == "Office" and created["product_count"] == 0
    assert client.post("/api/categories", json={"name": "office"}).status_code == 409
    assert client.post("/api/categories", json={"name": ""}).status_code == 400
    assert client.put(f"/api/categories/{created['id']}", json={"name": "Office Supplies"}).get_json()["name"] == "Office Supplies"
    assert client.get("/api/categories").get_json()["items"][0]["name"] == "Office Supplies"
    assert client.delete(f"/api/categories/{created['id']}").status_code == 204
    assert client.get(f"/api/categories/{created['id']}").status_code == 404


def test_category_in_use_cannot_be_deleted(client, category):
    make_product(client, category_id=category["id"])
    response = client.delete(f"/api/categories/{category['id']}")
    assert response.status_code == 409
    assert "1 product(s)" in response.get_json()["error"]
    assert client.get("/api/categories").get_json()["items"][0]["product_count"] == 1


def test_supplier_crud_and_validation(client):
    created = client.post("/api/suppliers", json={"name": "Kumasi Office Mart", "email": "orders@kom.example.com"}).get_json()
    assert created["email"] == "orders@kom.example.com" and created["phone"] is None
    bad = client.post("/api/suppliers", json={"name": "X", "email": "not-an-email"})
    assert bad.status_code == 400 and "email" in bad.get_json()["details"]
    bad_phone = client.post("/api/suppliers", json={"name": "X", "phone": "1" * 31})
    assert bad_phone.status_code == 400 and "phone" in bad_phone.get_json()["details"]
    updated = client.put(f"/api/suppliers/{created['id']}", json={"name": "KOM", "phone": "+233 32 204 5566"}).get_json()
    assert updated["name"] == "KOM" and updated["phone"] == "+233 32 204 5566" and updated["email"] is None
    assert client.delete(f"/api/suppliers/{created['id']}").status_code == 204


def test_supplier_in_use_cannot_be_deleted(client, supplier):
    make_product(client, supplier_id=supplier["id"])
    assert client.delete(f"/api/suppliers/{supplier['id']}").status_code == 409


def test_foreign_keys_enforced_at_database_level(app, category):
    """Bypass the API: the schema itself must reject bad references."""
    import sqlite3
    import database
    with app.app_context():
        conn = database.get_db()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO products (sku, name, unit_price, category_id) VALUES ('X', 'x', 1, 999)")
        conn.execute("INSERT INTO products (sku, name, unit_price, category_id) VALUES ('X', 'x', 1, ?)", (category["id"],))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM categories WHERE id = ?", (category["id"],))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE products SET quantity_in_stock = -1 WHERE sku = 'X'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE products SET unit_price = -1 WHERE sku = 'X'")
