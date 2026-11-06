"""Stock operations: every endpoint, the no-negative rule, atomicity, concurrency."""

import threading

import pytest

import database
from models import stock as stock_model
from tests.conftest import make_product


def history(client, product_id):
    return client.get(f"/api/products/{product_id}/transactions").get_json()["items"]


def quantity(client, product_id):
    return client.get(f"/api/products/{product_id}").get_json()["quantity_in_stock"]


def ledger_total(items):
    """IN adds, OUT subtracts, ADJUSTMENT is signed."""
    return sum(t["quantity"] if t["type"] != "OUT" else -t["quantity"] for t in items)


# --------------------------------------------------------------------------- #
# Happy paths
# --------------------------------------------------------------------------- #


def test_stock_in_increases_quantity_and_logs(client, product):
    response = client.post("/api/stock/in", json={"product_id": product["id"], "quantity": 5,
                                                  "reason": "Purchase order", "note": "PO-1"})
    assert response.status_code == 201
    body = response.get_json()
    assert body["product"]["quantity_in_stock"] == 25
    assert body["transaction"]["type"] == "IN"
    assert body["transaction"]["quantity"] == 5
    assert body["transaction"]["reason"] == "Purchase order"
    assert body["transaction"]["note"] == "PO-1"
    assert quantity(client, product["id"]) == 25


def test_stock_out_decreases_quantity_and_logs(client, product):
    response = client.post("/api/stock/out", json={"product_id": product["id"], "quantity": 8})
    assert response.status_code == 201
    assert response.get_json()["product"]["quantity_in_stock"] == 12
    assert response.get_json()["transaction"]["reason"] == "Sale"  # default reason
    assert quantity(client, product["id"]) == 12


def test_stock_out_exactly_to_zero_is_allowed(client, product):
    response = client.post("/api/stock/out", json={"product_id": product["id"], "quantity": 20})
    assert response.status_code == 201
    assert response.get_json()["product"]["quantity_in_stock"] == 0
    assert response.get_json()["product"]["stock_status"] == "out"


def test_adjust_with_new_quantity_records_signed_delta(client, product):
    down = client.post("/api/stock/adjust", json={"product_id": product["id"], "new_quantity": 17}).get_json()
    assert down["transaction"]["type"] == "ADJUSTMENT" and down["transaction"]["quantity"] == -3
    assert down["product"]["quantity_in_stock"] == 17
    up = client.post("/api/stock/adjust", json={"product_id": product["id"], "delta": 4}).get_json()
    assert up["transaction"]["quantity"] == 4 and up["product"]["quantity_in_stock"] == 21
    assert quantity(client, product["id"]) == 21


def test_history_sums_to_quantity_after_mixed_operations(client, product):
    pid = product["id"]
    client.post("/api/stock/in", json={"product_id": pid, "quantity": 30})
    client.post("/api/stock/out", json={"product_id": pid, "quantity": 12})
    client.post("/api/stock/adjust", json={"product_id": pid, "delta": -2})
    client.post("/api/stock/out", json={"product_id": pid, "quantity": 36})  # exactly to zero
    client.post("/api/stock/adjust", json={"product_id": pid, "new_quantity": 9})
    items = history(client, pid)
    assert [t["type"] for t in items] == ["ADJUSTMENT", "OUT", "ADJUSTMENT", "OUT", "IN", "IN"]  # newest first
    assert ledger_total(items) == quantity(client, pid) == 9


def test_recent_transactions_endpoint_spans_products(client, product):
    other = make_product(client, sku="OTHER-1", quantity_in_stock=1)
    client.post("/api/stock/out", json={"product_id": other["id"], "quantity": 1})
    items = client.get("/api/stock/transactions?limit=10").get_json()["items"]
    assert {t["product_id"] for t in items} == {product["id"], other["id"]}
    assert items[0]["type"] == "OUT" and items[0]["sku"] == "OTHER-1"
    assert client.get("/api/stock/transactions?limit=0").status_code == 400
    assert client.get("/api/stock/transactions?limit=501").status_code == 400


# --------------------------------------------------------------------------- #
# The no-negative-stock rule
# --------------------------------------------------------------------------- #


def test_over_withdrawal_is_rejected_with_clear_message_and_no_side_effects(client, product):
    before = history(client, product["id"])
    response = client.post("/api/stock/out", json={"product_id": product["id"], "quantity": 21})
    assert response.status_code == 400
    body = response.get_json()
    assert "Insufficient stock" in body["error"] and "only 20 available" in body["error"]
    assert body["details"] == {"quantity": "Only 20 available."}
    assert quantity(client, product["id"]) == 20
    assert history(client, product["id"]) == before


def test_withdrawal_from_zero_stock_product_is_rejected(client):
    product = make_product(client, quantity_in_stock=0)
    response = client.post("/api/stock/out", json={"product_id": product["id"], "quantity": 1})
    assert response.status_code == 400
    assert quantity(client, product["id"]) == 0


def test_negative_adjustment_below_zero_is_rejected(client, product):
    response = client.post("/api/stock/adjust", json={"product_id": product["id"], "delta": -21})
    assert response.status_code == 400
    assert "negative" in response.get_json()["error"]
    assert quantity(client, product["id"]) == 20
    assert len(history(client, product["id"])) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"new_quantity": 20},                 # no change
        {"delta": 0},                         # zero delta
        {"new_quantity": 5, "delta": 1},      # both
        {},                                   # neither
        {"new_quantity": -1},                 # negative target
        {"new_quantity": 1.5},                # not an integer
    ],
)
def test_invalid_adjustments_return_400(client, product, payload):
    response = client.post("/api/stock/adjust", json={"product_id": product["id"], **payload})
    assert response.status_code == 400
    assert quantity(client, product["id"]) == 20


@pytest.mark.parametrize("quantity_value", [0, -1, 1.5, "abc", True, None, 10**12])
def test_invalid_quantities_are_rejected_for_in_and_out(client, product, quantity_value):
    for endpoint in ("/api/stock/in", "/api/stock/out"):
        response = client.post(endpoint, json={"product_id": product["id"], "quantity": quantity_value})
        assert response.status_code == 400, (endpoint, quantity_value, response.get_json())
        assert "quantity" in response.get_json()["details"]
    assert quantity(client, product["id"]) == 20


def test_unknown_product_returns_404(client):
    assert client.post("/api/stock/in", json={"product_id": 999, "quantity": 1}).status_code == 404
    assert client.get("/api/products/999/transactions").status_code == 404


# --------------------------------------------------------------------------- #
# Atomicity: quantity update and audit row succeed or fail together
# --------------------------------------------------------------------------- #


def test_failure_after_quantity_update_rolls_everything_back(app, client, product, monkeypatch):
    """Simulate a crash between the UPDATE and the audit INSERT."""

    def exploding_record(*args, **kwargs):
        raise RuntimeError("simulated crash after quantity update")

    monkeypatch.setattr(stock_model, "_record", exploding_record)
    response = client.post("/api/stock/in", json={"product_id": product["id"], "quantity": 5})
    assert response.status_code == 500
    assert response.get_json() == {"error": "Internal server error."}  # no stack trace leaked
    monkeypatch.undo()

    assert quantity(client, product["id"]) == 20          # quantity rolled back
    assert len(history(client, product["id"])) == 1       # no audit row either
    # The database is still usable afterwards.
    assert client.post("/api/stock/in", json={"product_id": product["id"], "quantity": 5}).status_code == 201


def test_database_check_constraint_is_the_last_line_of_defence(app, product):
    """Even raw SQL cannot push quantity below zero."""
    import sqlite3
    with app.app_context():
        conn = database.get_db()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE products SET quantity_in_stock = quantity_in_stock - 21 WHERE id = ?", (product["id"],))
        assert conn.execute("SELECT quantity_in_stock FROM products WHERE id = ?", (product["id"],)).fetchone()[0] == 20


# --------------------------------------------------------------------------- #
# Simultaneous updates
# --------------------------------------------------------------------------- #


def test_concurrent_withdrawals_never_oversell(app, client):
    """25 threads each try to take 1 unit from a stock of 10: exactly 10 succeed."""
    product = make_product(client, quantity_in_stock=10)
    results = []
    lock = threading.Lock()

    def worker():
        # Each thread gets its own test client (and therefore its own DB connection).
        response = app.test_client().post("/api/stock/out", json={"product_id": product["id"], "quantity": 1})
        with lock:
            results.append((response.status_code, response.get_json().get("error", "")))

    threads = [threading.Thread(target=worker) for _ in range(25)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    statuses = [status for status, _ in results]
    assert statuses.count(201) == 10
    assert statuses.count(400) == 15
    # Every rejection came from the application's own guard (a clear message),
    # not from the database CHECK constraint acting as a last resort.
    assert all(error.startswith("Insufficient stock") for status, error in results if status == 400)
    assert quantity(client, product["id"]) == 0
    items = history(client, product["id"])
    assert sum(t["type"] == "OUT" for t in items) == 10
    assert ledger_total(items) == 0


def test_concurrent_mixed_operations_keep_ledger_consistent(app, client):
    """Interleaved IN/OUT/ADJUST from many threads: the ledger must always equal the quantity."""
    product = make_product(client, quantity_in_stock=50)

    def worker(i):
        c = app.test_client()
        if i % 3 == 0:
            c.post("/api/stock/in", json={"product_id": product["id"], "quantity": 3})
        elif i % 3 == 1:
            c.post("/api/stock/out", json={"product_id": product["id"], "quantity": 4})
        else:
            c.post("/api/stock/adjust", json={"product_id": product["id"], "delta": -1})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    items = history(client, product["id"])
    assert ledger_total(items) == quantity(client, product["id"]) >= 0
