#!/usr/bin/env python3
"""
Live smoke tests for Auspify IMS (functionality + security).

Runs against a RUNNING backend and prints one PASS/FAIL line per check.
Only the Python standard library is used, so no extra installs are needed.

    python scripts/smoke_test.py                              # all steps
    python scripts/smoke_test.py --base http://localhost:5173 # via the Vite proxy
    python scripts/smoke_test.py --only 1                     # just Step 1 checks

The script creates its own records (SKUs/names prefixed "SMOKE") and deletes
them again, so it can be re-run safely against the development database.
Exit code is 0 when every check passed, 1 otherwise.
"""

import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.request

# --------------------------------------------------------------------------- #
# Tiny HTTP client + result collector
# --------------------------------------------------------------------------- #


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def request(self, method, path, body=None, headers=None, raw=None):
        """Return (status, headers-dict, parsed-json-or-text)."""
        hdrs = dict(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            hdrs.setdefault("Content-Type", "application/json")
        if raw is not None:
            data = raw
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, dict(resp.headers), _parse(resp.read())
        except urllib.error.HTTPError as err:
            return err.code, dict(err.headers), _parse(err.read())

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body=body, **kw)

    def put(self, path, body=None, **kw):
        return self.request("PUT", path, body=body, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)


def _parse(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode(errors="replace")


class Checker:
    def __init__(self):
        self.passed = 0
        self.failed = 0

    def check(self, name, condition, detail=""):
        ok = bool(condition)
        self.passed += ok
        self.failed += not ok
        line = f"[{'PASS' if ok else 'FAIL'}] {name}"
        if not ok and detail:
            line += f"\n       -> {detail}"
        print(line)
        return ok

    def section(self, title):
        print(f"\n--- {title} ---")


def _h(headers, name):
    """Case-insensitive header lookup."""
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


# --------------------------------------------------------------------------- #
# Step 0
# --------------------------------------------------------------------------- #


def step0(c, k):
    k.section("Step 0: health")
    status, _, body = c.get("/api/health")
    k.check("GET /api/health -> 200 {status: ok}", status == 200 and body and body.get("status") == "ok", body)


# --------------------------------------------------------------------------- #
# Step 1: schema, seed, CRUD, validation + security
# --------------------------------------------------------------------------- #


def step1(c, k):
    tag = str(int(time.time()))[-6:]  # unique suffix so re-runs never collide
    created = {"products": [], "categories": [], "suppliers": []}

    try:
        _step1_functional(c, k, tag, created)
        _step1_security(c, k, tag, created)
    finally:
        _cleanup(c, created)
        # Verify the cleanup itself so the dev database stays tidy.
        k.section("Step 1: cleanup")
        status, _, body = c.get("/api/products")
        leftovers = [p for p in body["items"] if p["sku"].startswith("SMOKE")] if status == 200 else ["?"]
        k.check("All SMOKE test records removed", status == 200 and not leftovers, leftovers)


def _cleanup(c, created):
    for pid in created["products"]:
        c.delete(f"/api/products/{pid}")
    for cid in created["categories"]:
        c.delete(f"/api/categories/{cid}")
    for sid in created["suppliers"]:
        c.delete(f"/api/suppliers/{sid}")


def _step1_functional(c, k, tag, created):
    k.section("Step 1: seed data loaded")
    s, _, cats = c.get("/api/categories")
    k.check("GET /api/categories -> 200 with >= 5 categories", s == 200 and len(cats["items"]) >= 5, cats)
    s, _, sups = c.get("/api/suppliers")
    k.check("GET /api/suppliers -> 200 with >= 3 suppliers", s == 200 and len(sups["items"]) >= 3, sups)
    s, _, prods = c.get("/api/products")
    k.check("GET /api/products -> 200 with >= 20 products", s == 200 and prods["total"] >= 20, prods and prods.get("total"))
    k.check("products: total == len(items)", prods["total"] == len(prods["items"]))
    k.check("products include joined category_name & supplier_name",
            all("category_name" in p and "supplier_name" in p for p in prods["items"]))

    k.section("Step 1: category CRUD")
    s, _, cat = c.post("/api/categories", {"name": f"SMOKE Category {tag}"})
    k.check("POST category -> 201", s == 201 and cat.get("id"), (s, cat))
    created["categories"].append(cat["id"])
    s, _, dup = c.post("/api/categories", {"name": f"smoke category {tag}"})
    k.check("Duplicate category name (different case) -> 409", s == 409, (s, dup))
    s, _, upd = c.put(f"/api/categories/{cat['id']}", {"name": f"SMOKE Category {tag} v2"})
    k.check("PUT category -> 200 and name updated", s == 200 and upd["name"].endswith("v2"), (s, upd))
    s, _, body = c.post("/api/categories", {"name": "   "})
    k.check("Blank category name -> 400 with details.name", s == 400 and "name" in body.get("details", {}), (s, body))

    k.section("Step 1: supplier CRUD")
    s, _, sup = c.post("/api/suppliers", {"name": f"SMOKE Supplier {tag}", "email": "smoke@example.com", "phone": "+233 20 000 0000"})
    k.check("POST supplier -> 201 with email & phone", s == 201 and sup.get("email") == "smoke@example.com", (s, sup))
    created["suppliers"].append(sup["id"])
    s, _, body = c.post("/api/suppliers", {"name": "SMOKE Bad Email", "email": "not-an-email"})
    k.check("Invalid supplier email -> 400 details.email", s == 400 and "email" in body.get("details", {}), (s, body))
    s, _, upd = c.put(f"/api/suppliers/{sup['id']}", {"name": f"SMOKE Supplier {tag}", "phone": "+233 20 111 1111"})
    k.check("PUT supplier -> 200, phone updated, email cleared", s == 200 and upd["phone"].endswith("1111") and upd["email"] is None, (s, upd))

    k.section("Step 1: product CRUD")
    payload = {
        "sku": f"SMOKE-{tag}", "name": f"SMOKE Widget {tag}", "description": "temporary",
        "category_id": cat["id"], "supplier_id": sup["id"],
        "unit_price": 19.99, "quantity_in_stock": 5, "reorder_level": 2,
    }
    s, _, prod = c.post("/api/products", payload)
    k.check("POST product -> 201", s == 201 and prod.get("id"), (s, prod))
    created["products"].append(prod["id"])
    k.check("Created product echoes fields + joined names",
            prod["sku"] == payload["sku"] and prod["unit_price"] == 19.99 and prod["quantity_in_stock"] == 5
            and prod["category_name"].startswith("SMOKE Category") and prod["supplier_name"].startswith("SMOKE Supplier"), prod)
    s, _, got = c.get(f"/api/products/{prod['id']}")
    k.check("GET product by id -> 200 same record", s == 200 and got["id"] == prod["id"], (s, got))

    s, _, body = c.post("/api/products", dict(payload, name="dup"))
    k.check("Duplicate SKU -> 409", s == 409, (s, body))
    s, _, body = c.post("/api/products", dict(payload, sku=payload["sku"].lower(), name="dup"))
    k.check("Duplicate SKU (different case) -> 409", s == 409, (s, body))

    s, _, body = c.post("/api/products", dict(payload, sku=f"SMOKE-NEG-{tag}", unit_price=-1))
    k.check("Negative unit_price -> 400 details.unit_price", s == 400 and "unit_price" in body.get("details", {}), (s, body))
    s, _, body = c.post("/api/products", dict(payload, sku=f"SMOKE-NEG-{tag}", quantity_in_stock=-3))
    k.check("Negative quantity_in_stock -> 400 details.quantity_in_stock", s == 400 and "quantity_in_stock" in body.get("details", {}), (s, body))
    s, _, body = c.post("/api/products", dict(payload, sku=f"SMOKE-NEG-{tag}", reorder_level=-1))
    k.check("Negative reorder_level -> 400", s == 400 and "reorder_level" in body.get("details", {}), (s, body))
    s, _, body = c.post("/api/products", {"unit_price": 1})
    k.check("Missing sku AND name -> 400 listing both fields", s == 400 and {"sku", "name"} <= set(body.get("details", {})), (s, body))
    s, _, body = c.post("/api/products", dict(payload, sku=f"SMOKE-DEC-{tag}", unit_price="12.345"))
    k.check("Decimal price string '12.345' accepted and rounded to 12.35", s == 201 and body["unit_price"] == 12.35, (s, body))
    if s == 201:
        created["products"].append(body["id"])

    k.section("Step 1: foreign keys enforced")
    s, _, body = c.post("/api/products", dict(payload, sku=f"SMOKE-FK-{tag}", category_id=999999))
    k.check("Unknown category_id -> 400 details.category_id", s == 400 and "category_id" in body.get("details", {}), (s, body))
    s, _, body = c.post("/api/products", dict(payload, sku=f"SMOKE-FK-{tag}", supplier_id=999999))
    k.check("Unknown supplier_id -> 400 details.supplier_id", s == 400 and "supplier_id" in body.get("details", {}), (s, body))
    s, _, body = c.delete(f"/api/categories/{cat['id']}")
    k.check("Delete category still used by a product -> 409", s == 409, (s, body))
    s, _, body = c.delete(f"/api/suppliers/{sup['id']}")
    k.check("Delete supplier still used by a product -> 409", s == 409, (s, body))

    k.section("Step 1: product update / delete")
    s, _, upd = c.put(f"/api/products/{prod['id']}", {"name": "SMOKE Widget renamed", "unit_price": 25})
    k.check("PUT product -> 200 name & price updated, other fields kept",
            s == 200 and upd["name"] == "SMOKE Widget renamed" and upd["unit_price"] == 25.0 and upd["sku"] == payload["sku"], (s, upd))
    k.check("updated_at changed after update", upd["updated_at"] >= prod["updated_at"])
    s, _, body = c.put(f"/api/products/{prod['id']}", {"quantity_in_stock": 99})
    k.check("PUT quantity_in_stock directly -> 400 (must use stock movements)", s == 400 and "quantity_in_stock" in body.get("details", {}), (s, body))
    seeded_sku = [p for p in c.get("/api/products")[2]["items"] if not p["sku"].startswith("SMOKE")][0]["sku"]
    s, _, body = c.put(f"/api/products/{prod['id']}", {"sku": seeded_sku})
    k.check("PUT sku to one that already exists -> 409", s == 409, (s, body))
    s, _, body = c.get("/api/products/999999")
    k.check("GET unknown product -> 404 JSON error", s == 404 and body.get("error"), (s, body))

    s, _, _ = c.delete(f"/api/products/{prod['id']}")
    k.check("DELETE product -> 204", s == 204, s)
    created["products"].remove(prod["id"])
    s, _, _ = c.get(f"/api/products/{prod['id']}")
    k.check("GET deleted product -> 404", s == 404, s)
    s, _, body = c.delete(f"/api/products/{prod['id']}")
    k.check("DELETE already-deleted product -> 404", s == 404, (s, body))


def _step1_security(c, k, tag, created):
    k.section("Step 1: security - malformed input")
    s, _, body = c.post("/api/products", raw=b"{not json", headers={"Content-Type": "application/json"})
    k.check("Malformed JSON -> 400 JSON error (no 500)", s == 400 and isinstance(body, dict) and body.get("error"), (s, body))
    s, _, body = c.post("/api/products", body=["a", "list"])
    k.check("JSON array instead of object -> 400", s == 400, (s, body))
    s, _, body = c.post("/api/products", raw=b"sku=X&name=Y", headers={"Content-Type": "application/x-www-form-urlencoded"})
    k.check("Form-encoded body -> 400 (JSON required)", s == 400, (s, body))
    s, _, body = c.post("/api/products", raw=b"", headers={"Content-Type": "application/json"})
    k.check("Empty body -> 400", s == 400, (s, body))
    big = json.dumps({"sku": f"SMOKE-BIG-{tag}", "name": "x" * (1024 * 1024 + 100), "unit_price": 1}).encode()
    s, _, body = c.post("/api/products", raw=big, headers={"Content-Type": "application/json"})
    k.check("Body > 1 MB -> 413 JSON error", s == 413 and isinstance(body, dict), (s, str(body)[:80]))

    k.section("Step 1: security - type confusion")
    base = {"sku": f"SMOKE-T-{tag}", "name": "SMOKE type test", "unit_price": 1}
    s, _, body = c.post("/api/products", dict(base, name=["an", "array"]))
    k.check("name as array -> 400 details.name", s == 400 and "name" in body.get("details", {}), (s, body))
    s, _, body = c.post("/api/products", dict(base, unit_price=True))
    k.check("unit_price as boolean -> 400", s == 400 and "unit_price" in body.get("details", {}), (s, body))
    s, _, body = c.post("/api/products", dict(base, unit_price="NaN"))
    k.check("unit_price 'NaN' -> 400", s == 400 and "unit_price" in body.get("details", {}), (s, body))
    s, _, body = c.post("/api/products", dict(base, quantity_in_stock=1.5))
    k.check("quantity_in_stock 1.5 -> 400", s == 400 and "quantity_in_stock" in body.get("details", {}), (s, body))
    s, _, body = c.post("/api/products", dict(base, category_id="1 OR 1=1"))
    k.check("category_id '1 OR 1=1' -> 400", s == 400 and "category_id" in body.get("details", {}), (s, body))
    s, _, body = c.post("/api/products", dict(base, name="bad\x00name"))
    k.check("Null byte in name -> 400", s == 400, (s, body))
    s, _, body = c.post("/api/products", dict(base, name="n" * 101))
    k.check("Name longer than 100 chars -> 400", s == 400 and "name" in body.get("details", {}), (s, body))
    s, _, body = c.post("/api/products", dict(base, sku="BAD SKU; DROP TABLE products;--"))
    k.check("SKU with spaces/punctuation -> 400 (format whitelist)", s == 400 and "sku" in body.get("details", {}), (s, body))
    s, _, body = c.post("/api/products", dict(base, unit_price=1, bogus_field="ignored", id=1))
    k.check("Unknown / id fields are ignored, product still created", s == 201 and body["id"] != 1, (s, body))
    if s == 201:
        created["products"].append(body["id"])

    k.section("Step 1: security - injection payloads stored literally")
    before = c.get("/api/products")[2]["total"]
    inj_name = "Robert'); DROP TABLE products;--"
    s, _, body = c.post("/api/products", {"sku": f"SMOKE-INJ-{tag}", "name": inj_name, "unit_price": 1})
    k.check("SQL-injection string in name -> stored literally, 201", s == 201 and body["name"] == inj_name, (s, body))
    if s == 201:
        created["products"].append(body["id"])
    s, _, after = c.get("/api/products")
    k.check("products table intact after injection attempt (count +1)", s == 200 and after["total"] == before + 1, (before, after.get("total")))
    xss = "<img src=x onerror=alert(1)>"
    s, hdrs, body = c.post("/api/products", {"sku": f"SMOKE-XSS-{tag}", "name": xss, "unit_price": 1})
    k.check("XSS string stored as plain data (201)", s == 201 and body["name"] == xss, (s, body))
    if s == 201:
        created["products"].append(body["id"])
    k.check("Response is application/json (browser will not render it as HTML)",
            (_h(hdrs, "Content-Type") or "").startswith("application/json"), _h(hdrs, "Content-Type"))

    k.section("Step 1: security - headers, CORS, routing")
    s, hdrs, _ = c.get("/api/products")
    k.check("X-Content-Type-Options: nosniff", _h(hdrs, "X-Content-Type-Options") == "nosniff", hdrs)
    k.check("X-Frame-Options: DENY", _h(hdrs, "X-Frame-Options") == "DENY")
    k.check("Cache-Control: no-store", _h(hdrs, "Cache-Control") == "no-store")
    s, hdrs, _ = c.get("/api/products", headers={"Origin": "http://evil.example"})
    k.check("CORS: unknown origin gets NO Access-Control-Allow-Origin", _h(hdrs, "Access-Control-Allow-Origin") is None, _h(hdrs, "Access-Control-Allow-Origin"))
    s, hdrs, _ = c.get("/api/products", headers={"Origin": "http://localhost:5173"})
    k.check("CORS: allowed origin echoed back", _h(hdrs, "Access-Control-Allow-Origin") == "http://localhost:5173", _h(hdrs, "Access-Control-Allow-Origin"))
    s, _, body = c.get("/api/does-not-exist")
    k.check("Unknown route -> 404 JSON", s == 404 and isinstance(body, dict) and body.get("error"), (s, body))
    s, _, body = c.request("PATCH", "/api/products")
    k.check("Wrong method -> 405 JSON", s == 405 and isinstance(body, dict), (s, body))
    s, _, body = c.get("/api/products/abc")
    k.check("Non-integer id -> 404 JSON", s == 404 and isinstance(body, dict), (s, body))
    s, _, body = c.get("/api/products/-1")
    k.check("Negative id -> 404 JSON", s == 404 and isinstance(body, dict), (s, body))
    s, _, body = c.get("/api/products/99999999999999999999")
    k.check("Huge id -> 404 JSON (no crash)", s == 404 and isinstance(body, dict), (s, body))
    s, _, body = c.get("/api/products/0")
    k.check("Id 0 -> 404 JSON", s == 404 and isinstance(body, dict), (s, body))
    s, _, body = c.post("/api/products", {"sku": f"SMOKE-HUGE-{tag}", "name": "x", "unit_price": 1,
                                          "category_id": 99999999999999999999})
    k.check("Huge category_id in body -> 400 (no crash)", s == 400 and "category_id" in body.get("details", {}), (s, body))


# --------------------------------------------------------------------------- #
# Step 2: stock management
# --------------------------------------------------------------------------- #


def _tx_sum(items):
    """Apply the audit rule: IN adds, OUT subtracts, ADJUSTMENT is signed."""
    total = 0
    for t in items:
        if t["type"] == "IN":
            total += t["quantity"]
        elif t["type"] == "OUT":
            total -= t["quantity"]
        else:
            total += t["quantity"]
    return total


def step2(c, k):
    tag = str(int(time.time()))[-6:]
    created = {"products": [], "categories": [], "suppliers": []}
    try:
        _step2_operations(c, k, tag, created)
        _step2_badges(c, k, tag, created)
        _step2_concurrency(c, k, tag, created)
        _step2_security(c, k, tag, created)
    finally:
        _cleanup(c, created)


def _qty(c, pid):
    return c.get(f"/api/products/{pid}")[2]["quantity_in_stock"]


def _history(c, pid):
    return c.get(f"/api/products/{pid}/transactions")[2]["items"]


def _step2_operations(c, k, tag, created):
    k.section("Step 2: stock in / out / adjust")
    s, _, prod = c.post("/api/products", {"sku": f"SMOKE-STK-{tag}", "name": "SMOKE stock item",
                                          "unit_price": 10, "quantity_in_stock": 10, "reorder_level": 5})
    k.check("Create product with initial quantity 10 -> 201", s == 201, (s, prod))
    pid = prod["id"]
    created["products"].append(pid)
    hist = _history(c, pid)
    k.check("Initial quantity produced ONE 'Initial stock' IN transaction",
            len(hist) == 1 and hist[0]["type"] == "IN" and hist[0]["quantity"] == 10 and hist[0]["reason"] == "Initial stock", hist)

    s, _, body = c.post("/api/stock/in", {"product_id": pid, "quantity": 5, "reason": "Purchase order", "note": "PO-77"})
    k.check("POST /api/stock/in +5 -> 201, product qty 15", s == 201 and body["product"]["quantity_in_stock"] == 15, (s, body))
    k.check("  transaction row: IN 5, reason/note stored",
            body["transaction"]["type"] == "IN" and body["transaction"]["quantity"] == 5
            and body["transaction"]["reason"] == "Purchase order" and body["transaction"]["note"] == "PO-77", body.get("transaction"))

    s, _, body = c.post("/api/stock/out", {"product_id": pid, "quantity": 4})
    k.check("POST /api/stock/out 4 -> 201, product qty 11", s == 201 and body["product"]["quantity_in_stock"] == 11, (s, body))
    k.check("  transaction row: OUT 4 with default reason 'Sale'",
            body["transaction"]["type"] == "OUT" and body["transaction"]["quantity"] == 4 and body["transaction"]["reason"] == "Sale", body.get("transaction"))

    before_hist = len(_history(c, pid))
    s, _, body = c.post("/api/stock/out", {"product_id": pid, "quantity": 100})
    k.check("Over-withdrawal (100 of 11) -> 400 with clear message",
            s == 400 and "Insufficient stock" in body.get("error", "") and "11 available" in body["error"], (s, body))
    k.check("  quantity unchanged (still 11)", _qty(c, pid) == 11, _qty(c, pid))
    k.check("  no transaction row written for the failed operation", len(_history(c, pid)) == before_hist, (before_hist, len(_history(c, pid))))

    s, _, body = c.post("/api/stock/out", {"product_id": pid, "quantity": 11})
    k.check("Withdraw exactly the remaining 11 -> 201, qty 0 (boundary allowed)", s == 201 and body["product"]["quantity_in_stock"] == 0, (s, body))
    s, _, body = c.post("/api/stock/out", {"product_id": pid, "quantity": 1})
    k.check("Withdraw 1 from 0 -> 400", s == 400, (s, body))

    s, _, body = c.post("/api/stock/adjust", {"product_id": pid, "new_quantity": 8, "note": "Physical count"})
    k.check("Adjust new_quantity=8 from 0 -> 201, ADJUSTMENT +8, qty 8",
            s == 201 and body["transaction"]["type"] == "ADJUSTMENT" and body["transaction"]["quantity"] == 8
            and body["product"]["quantity_in_stock"] == 8, (s, body))
    s, _, body = c.post("/api/stock/adjust", {"product_id": pid, "delta": -3})
    k.check("Adjust delta=-3 -> 201, ADJUSTMENT -3, qty 5",
            s == 201 and body["transaction"]["quantity"] == -3 and body["product"]["quantity_in_stock"] == 5, (s, body))
    before_hist = len(_history(c, pid))
    s, _, body = c.post("/api/stock/adjust", {"product_id": pid, "delta": -50})
    k.check("Adjust delta=-50 (would go negative) -> 400, qty still 5, no row",
            s == 400 and _qty(c, pid) == 5 and len(_history(c, pid)) == before_hist, (s, body))
    s, _, body = c.post("/api/stock/adjust", {"product_id": pid, "new_quantity": 5})
    k.check("Adjust to the current quantity -> 400 'no change'", s == 400, (s, body))
    s, _, body = c.post("/api/stock/adjust", {"product_id": pid, "new_quantity": 5, "delta": 1})
    k.check("Adjust with BOTH new_quantity and delta -> 400", s == 400, (s, body))
    s, _, body = c.post("/api/stock/adjust", {"product_id": pid})
    k.check("Adjust with NEITHER -> 400", s == 400, (s, body))
    s, _, body = c.post("/api/stock/adjust", {"product_id": pid, "delta": 0})
    k.check("Adjust delta=0 -> 400", s == 400, (s, body))

    k.section("Step 2: history is a complete audit trail")
    hist = _history(c, pid)
    k.check("Transaction types recorded: IN, OUT, ADJUSTMENT", {t["type"] for t in hist} == {"IN", "OUT", "ADJUSTMENT"}, hist)
    k.check("Sum of transactions == current quantity (5)", _tx_sum(hist) == 5 == _qty(c, pid), (_tx_sum(hist), _qty(c, pid)))
    k.check("History is newest first", all(hist[i]["id"] >= hist[i + 1]["id"] for i in range(len(hist) - 1)))
    s, _, body = c.get("/api/products/999999/transactions")
    k.check("History of unknown product -> 404", s == 404, (s, body))
    s, _, body = c.get("/api/stock/transactions?limit=5")
    k.check("GET /api/stock/transactions?limit=5 -> 200, 5 most recent", s == 200 and len(body["items"]) == 5, (s, body))

    k.section("Step 2: input validation")
    for payload, label in [
        ({"product_id": pid, "quantity": 0}, "quantity 0"),
        ({"product_id": pid, "quantity": -1}, "quantity -1"),
        ({"product_id": pid, "quantity": 1.5}, "quantity 1.5"),
        ({"product_id": pid, "quantity": "abc"}, "quantity 'abc'"),
        ({"product_id": pid, "quantity": True}, "quantity true"),
        ({"product_id": pid, "quantity": 10**12}, "quantity 1e12 (above cap)"),
        ({"quantity": 1}, "missing product_id"),
        ({"product_id": "1; DROP TABLE products", "quantity": 1}, "product_id injection string"),
        ({"product_id": 99999999999999999999, "quantity": 1}, "huge product_id"),
    ]:
        s, _, body = c.post("/api/stock/in", payload)
        k.check(f"stock/in with {label} -> 400", s == 400 and isinstance(body, dict) and body.get("details"), (s, body))
    s, _, body = c.post("/api/stock/in", {"product_id": 999999, "quantity": 1})
    k.check("stock/in for unknown product -> 404", s == 404, (s, body))


def _step2_badges(c, k, tag, created):
    k.section("Step 2: stock_status (badge logic)")
    s, _, prod = c.post("/api/products", {"sku": f"SMOKE-BDG-{tag}", "name": "SMOKE badge item",
                                          "unit_price": 1, "quantity_in_stock": 0, "reorder_level": 3})
    pid = prod["id"]
    created["products"].append(pid)
    k.check("qty 0, reorder 3 -> 'out'", prod["stock_status"] == "out", prod["stock_status"])
    s, _, body = c.post("/api/stock/in", {"product_id": pid, "quantity": 1})
    k.check("qty 1 -> 'low'", body["product"]["stock_status"] == "low", body["product"]["stock_status"])
    s, _, body = c.post("/api/stock/in", {"product_id": pid, "quantity": 2})
    k.check("qty 3 (== reorder level) -> 'low'", body["product"]["stock_status"] == "low", body["product"]["stock_status"])
    s, _, body = c.post("/api/stock/in", {"product_id": pid, "quantity": 1})
    k.check("qty 4 (> reorder level) -> 'in_stock'", body["product"]["stock_status"] == "in_stock", body["product"]["stock_status"])
    s, _, body = c.put(f"/api/products/{pid}", {"reorder_level": 10})
    k.check("raising reorder_level to 10 -> 'low' again", body["stock_status"] == "low", body)
    s, _, body = c.get("/api/products")
    k.check("every product in the list carries a stock_status",
            all(p.get("stock_status") in ("in_stock", "low", "out") for p in body["items"]))


def _step2_concurrency(c, k, tag, created):
    import concurrent.futures

    k.section("Step 2: concurrency - 20 simultaneous withdrawals of 1 from a stock of 10")
    s, _, prod = c.post("/api/products", {"sku": f"SMOKE-CC-{tag}", "name": "SMOKE concurrency item",
                                          "unit_price": 1, "quantity_in_stock": 10})
    pid = prod["id"]
    created["products"].append(pid)

    def withdraw(_):
        return c.post("/api/stock/out", {"product_id": pid, "quantity": 1})[0]

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        statuses = list(pool.map(withdraw, range(20)))
    ok = statuses.count(201)
    rejected = statuses.count(400)
    k.check("exactly 10 succeeded (201) and 10 were rejected (400)", ok == 10 and rejected == 10, statuses)
    k.check("final quantity is 0, never negative", _qty(c, pid) == 0, _qty(c, pid))
    hist = _history(c, pid)
    k.check("exactly 10 OUT rows recorded (+1 initial IN)", sum(t["type"] == "OUT" for t in hist) == 10 and len(hist) == 11, len(hist))
    k.check("history sums to the final quantity", _tx_sum(hist) == 0, _tx_sum(hist))


def _step2_security(c, k, tag, created):
    k.section("Step 2: security")
    pid = created["products"][0]
    s, _, body = c.post("/api/stock/in", {"product_id": pid, "quantity": 1, "note": "n" * 1001})
    k.check("note longer than 1000 chars -> 400", s == 400 and "note" in body.get("details", {}), (s, body))
    s, _, body = c.post("/api/stock/in", {"product_id": pid, "quantity": 1, "reason": "r" * 101})
    k.check("reason longer than 100 chars -> 400", s == 400 and "reason" in body.get("details", {}), (s, body))
    s, _, body = c.post("/api/stock/in", {"product_id": pid, "quantity": 1, "reason": ["not", "text"]})
    k.check("reason as array -> 400", s == 400, (s, body))
    xss = "<script>alert('x')</script>"
    s, _, body = c.post("/api/stock/in", {"product_id": pid, "quantity": 1, "note": xss, "reason": "'; DELETE FROM stock_transactions; --"})
    k.check("XSS/SQL strings in note/reason stored literally, tables intact",
            s == 201 and body["transaction"]["note"] == xss and len(_history(c, pid)) >= 2, (s, body))
    s, _, body = c.post("/api/stock/in", raw=b"{bad json", headers={"Content-Type": "application/json"})
    k.check("malformed JSON to stock/in -> 400", s == 400, (s, body))
    s, _, body = c.get("/api/stock/in")
    k.check("GET /api/stock/in -> 405 JSON", s == 405 and isinstance(body, dict), (s, body))
    s, _, body = c.put("/api/stock/out", {"product_id": pid, "quantity": 1})
    k.check("PUT /api/stock/out -> 405 JSON", s == 405 and isinstance(body, dict), (s, body))
    for bad in ("0", "-5", "abc", "10000"):
        s, _, body = c.get(f"/api/stock/transactions?limit={bad}")
        k.check(f"GET /api/stock/transactions?limit={bad} -> 400", s == 400 and isinstance(body, dict), (s, body))
    s, _, body = c.get(f"/api/products/{pid}/transactions?limit=1%27%20OR%201=1")
    k.check("limit with SQL injection -> 400", s == 400, (s, body))


# --------------------------------------------------------------------------- #
# Step 3: reports
# --------------------------------------------------------------------------- #


def step3(c, k):
    import datetime as dt

    tag = str(int(time.time()))[-6:]
    created = {"products": [], "categories": [], "suppliers": []}
    try:
        k.section("Step 3: summary matches independent calculation")
        products = c.get("/api/products")[2]["items"]
        s, _, summ = c.get("/api/reports/summary")
        k.check("GET /api/reports/summary -> 200", s == 200, (s, summ))
        exp_units = sum(p["quantity_in_stock"] for p in products)
        exp_value = round(sum(p["quantity_in_stock"] * p["unit_price"] for p in products), 2)
        exp_low = sum(p["stock_status"] == "low" for p in products)
        exp_out = sum(p["stock_status"] == "out" for p in products)
        k.check(f"total_products == {len(products)}", summ["total_products"] == len(products), summ)
        k.check(f"total_units == {exp_units}", summ["total_units"] == exp_units, summ)
        k.check(f"total_value == {exp_value}", abs(summ["total_value"] - exp_value) < 0.01, summ)
        k.check(f"low_stock_count == {exp_low}", summ["low_stock_count"] == exp_low, summ)
        k.check(f"out_of_stock_count == {exp_out}", summ["out_of_stock_count"] == exp_out, summ)

        k.section("Step 3: low-stock report")
        s, _, low = c.get("/api/reports/low-stock")
        expected_ids = {p["id"] for p in products if p["quantity_in_stock"] <= p["reorder_level"]}
        k.check("contains exactly the products with qty <= reorder_level",
                s == 200 and {i["id"] for i in low["items"]} == expected_ids and low["total"] == len(expected_ids), (s, low.get("total"), len(expected_ids)))
        k.check("sorted by quantity ascending (most urgent first)",
                [i["quantity_in_stock"] for i in low["items"]] == sorted(i["quantity_in_stock"] for i in low["items"]))
        k.check("each row carries shortfall = reorder_level - quantity and a stock_status",
                all(i["shortfall"] == i["reorder_level"] - i["quantity_in_stock"] and i["stock_status"] in ("low", "out") for i in low["items"]))

        k.section("Step 3: valuation by category")
        s, _, val = c.get("/api/reports/valuation-by-category")
        k.check("category values sum to summary total_value",
                s == 200 and abs(sum(i["total_value"] for i in val["items"]) - summ["total_value"]) < 0.01, (val.get("total_value"), summ["total_value"]))
        k.check("category product counts sum to total_products",
                sum(i["product_count"] for i in val["items"]) == summ["total_products"])
        k.check("sorted by value descending",
                [i["total_value"] for i in val["items"]] == sorted((i["total_value"] for i in val["items"]), reverse=True))
        for cat in val["items"][:2]:
            mine = [p for p in products if p["category_id"] == cat["category_id"]]
            k.check(f"  '{cat['category_name']}' value matches sum over its products",
                    abs(round(sum(p["quantity_in_stock"] * p["unit_price"] for p in mine), 2) - cat["total_value"]) < 0.01, cat)

        k.section("Step 3: movements over a date range")
        today = dt.date.today()
        s, _, mv = c.get("/api/reports/movements")
        k.check("default range is the last 30 days ending today",
                s == 200 and len(mv["days"]) == 30 and mv["to"] == today.isoformat(), (s, mv.get("from"), mv.get("to"), len(mv.get("days", []))))
        k.check("totals equal the sum of the daily buckets",
                all(mv["totals"][f] == sum(d[f] for d in mv["days"]) for f in ("stock_in", "stock_out", "adjustments", "transactions")))
        k.check("net = in - out + adjustments for every day",
                all(d["net"] == d["stock_in"] - d["stock_out"] + d["adjustments"] for d in mv["days"]))
        # Record known movements today and confirm today's bucket moves by exactly that amount.
        s, _, prod = c.post("/api/products", {"sku": f"SMOKE-RPT-{tag}", "name": "SMOKE report item", "unit_price": 2.5, "quantity_in_stock": 0})
        created["products"].append(prod["id"])
        before = c.get(f"/api/reports/movements?from={today}&to={today}")[2]["days"][0]
        c.post("/api/stock/in", {"product_id": prod["id"], "quantity": 40})
        c.post("/api/stock/out", {"product_id": prod["id"], "quantity": 15})
        after = c.get(f"/api/reports/movements?from={today}&to={today}")[2]["days"][0]
        k.check("single-day range returns exactly one bucket for today", after["day"] == today.isoformat(), after)
        k.check("today's stock_in rose by 40 and stock_out by 15",
                after["stock_in"] - before["stock_in"] == 40 and after["stock_out"] - before["stock_out"] == 15, (before, after))
        far = c.get("/api/reports/movements?from=2000-01-01&to=2000-01-07")[2]
        k.check("range with no data returns 7 zero-filled days (not an error)",
                len(far["days"]) == 7 and far["totals"]["transactions"] == 0, far["totals"])
        three = c.get(f"/api/reports/movements?from={today - dt.timedelta(days=2)}&to={today}")[2]
        k.check("3-day range -> 3 buckets in order", [d["day"] for d in three["days"]] == [(today - dt.timedelta(days=i)).isoformat() for i in (2, 1, 0)])
        for query, label in [("from=2026-13-45", "invalid date"), ("from=2026-11-10&to=2026-11-01", "from after to"),
                             ("from=2020-01-01&to=2026-01-01", "range > 366 days"), ("from=2026-01-01'%20OR%201=1--", "SQL injection in from"),
                             ("to=notadate", "invalid to")]:
            s, _, body = c.get(f"/api/reports/movements?{query}")
            k.check(f"movements with {label} -> 400", s == 400 and isinstance(body, dict) and body.get("details"), (s, body))

        k.section("Step 3: top moving products")
        s, _, top = c.get(f"/api/reports/top-moving-products?from={today}&to={today}&limit=3")
        k.check("limit=3 respected and sorted by units_out desc",
                s == 200 and len(top["items"]) <= 3 and [i["units_out"] for i in top["items"]] == sorted((i["units_out"] for i in top["items"]), reverse=True), (s, top))
        k.check("today's SMOKE product appears with units_out 15",
                any(i["id"] == prod["id"] and i["units_out"] == 15 and i["units_in"] == 40 for i in top["items"]), top)
        for bad in ("0", "51", "abc"):
            s, _, body = c.get(f"/api/reports/top-moving-products?limit={bad}")
            k.check(f"top-moving limit={bad} -> 400", s == 400, (s, body))

        k.section("Step 3: CSV export")
        s, hdrs, csv_text = c.get("/api/reports/low-stock?format=csv")
        lines = csv_text.strip().split("\r\n") if isinstance(csv_text, str) else []
        k.check("low-stock CSV -> 200 text/csv with attachment filename",
                s == 200 and (_h(hdrs, "Content-Type") or "").startswith("text/csv") and "attachment" in (_h(hdrs, "Content-Disposition") or ""), (s, hdrs))
        k.check("header row + one line per low-stock product",
                lines and lines[0] == "SKU,Product,Category,Supplier,Quantity,Reorder level,Shortfall,Unit price,Status"
                and len(lines) == 1 + c.get("/api/reports/low-stock")[2]["total"], (lines[:1], len(lines)))
        k.check("nosniff header also on CSV", _h(hdrs, "X-Content-Type-Options") == "nosniff")
        s, hdrs, body = c.get("/api/reports/valuation-by-category?format=csv")
        k.check("valuation CSV -> 200 text/csv", s == 200 and (_h(hdrs, "Content-Type") or "").startswith("text/csv"), (s, hdrs))
        s, _, body = c.get("/api/reports/low-stock?format=xml")
        k.check("format=xml -> 400", s == 400, (s, body))

        k.section("Step 3: security - CSV formula injection neutralised")
        evil_names = ['=HYPERLINK("http://evil.example","click")', "+1+1", "-2+3", "@SUM(A1)"]
        for i, name in enumerate(evil_names):
            s, _, p = c.post("/api/products", {"sku": f"SMOKE-CSV{i}-{tag}", "name": name, "unit_price": 1, "quantity_in_stock": 0})
            if s == 201:
                created["products"].append(p["id"])
        s, _, csv_text = c.get("/api/reports/low-stock?format=csv")
        rows = list(__import__("csv").reader(io.StringIO(csv_text)))
        cells = {r[1] for r in rows[1:]}
        for name in evil_names:
            k.check(f"CSV cell for {name[:14]!r} is prefixed with a quote", ("'" + name) in cells and name not in cells)
        s, _, body = c.get("/api/reports/low-stock")
        k.check("JSON output keeps the raw name (escaping is CSV-only)", any(i["name"] == evil_names[0] for i in body["items"]))
    finally:
        _cleanup(c, created)




# --------------------------------------------------------------------------- #
STEPS = {0: step0, 1: step1, 2: step2, 3: step3}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="http://localhost:5000", help="backend base URL")
    parser.add_argument("--only", type=int, help="run only this step's checks")
    args = parser.parse_args()

    client = Client(args.base)
    checker = Checker()
    print(f"Smoke tests against {client.base}")
    for number, fn in sorted(STEPS.items()):
        if args.only is None or args.only == number:
            fn(client, checker)

    print(f"\n==> {checker.passed} passed, {checker.failed} failed")
    sys.exit(1 if checker.failed else 0)


if __name__ == "__main__":
    main()
