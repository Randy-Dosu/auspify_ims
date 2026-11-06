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
STEPS = {0: step0, 1: step1}


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
