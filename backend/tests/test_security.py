"""
Security-focused checks: hostile input, protocol misuse and information leaks.
The SQL-injection and formula-injection cases live next to the features they
target (test_filters.py, test_reports.py); this file covers the cross-cutting
behaviour of the API as a whole.
"""

import json

import pytest

from tests.conftest import make_product

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


@pytest.mark.parametrize("path", ["/api/health", "/api/products", "/api/reports/summary",
                                  "/api/reports/low-stock?format=csv", "/api/does-not-exist"])
def test_every_response_carries_security_headers(client, path):
    response = client.get(path)
    for header, value in SECURITY_HEADERS.items():
        assert response.headers.get(header) == value, (path, header)


def test_unknown_routes_and_methods_return_json_not_html(client):
    missing = client.get("/api/nothing/here")
    assert missing.status_code == 404
    assert missing.mimetype == "application/json" and "error" in missing.get_json()
    wrong_method = client.delete("/api/reports/summary")
    assert wrong_method.status_code == 405
    assert wrong_method.mimetype == "application/json"
    assert b"<html" not in missing.data.lower() and b"<html" not in wrong_method.data.lower()


@pytest.mark.parametrize("body,content_type", [
    ("not json", "application/json"),
    ("[1, 2, 3]", "application/json"),
    ('"just a string"', "application/json"),
    ("sku=X&name=Y", "application/x-www-form-urlencoded"),
    ("", "application/json"),
])
def test_malformed_or_non_object_bodies_are_rejected(client, body, content_type):
    response = client.post("/api/products", data=body, content_type=content_type)
    assert response.status_code == 400
    assert "JSON object" in response.get_json()["error"]


def test_oversized_bodies_are_rejected_with_413(client):
    huge = {"sku": "BIG-1", "name": "x", "unit_price": 1, "description": "a" * (1024 * 1024 + 10)}
    response = client.post("/api/products", data=json.dumps(huge), content_type="application/json")
    assert response.status_code == 413
    assert response.mimetype == "application/json"
    assert client.get("/api/products").get_json()["total"] == 0


def test_unexpected_fields_are_ignored_not_stored(client):
    """Mass-assignment guard: clients cannot set columns the API does not expose."""
    response = client.post("/api/products", json={
        "sku": "MA-1", "name": "Mass assign", "unit_price": 5,
        "id": 9999, "created_at": "1999-01-01T00:00:00Z", "is_admin": True,
    })
    assert response.status_code == 201
    body = response.get_json()
    assert body["id"] != 9999 and not body["created_at"].startswith("1999")
    assert "is_admin" not in body


def test_html_in_text_fields_is_stored_verbatim_and_returned_as_json(client, category):
    """
    The API never renders HTML, so it stores what it is given; the React UI
    escapes text when rendering. We assert the payload is JSON-encoded (so a
    browser hitting the API directly cannot be tricked into executing it).
    """
    name = "<img src=x onerror=alert(1)>"
    created = make_product(client, name=name, category_id=category["id"])
    assert created["name"] == name
    response = client.get(f"/api/products/{created['id']}")
    assert response.mimetype == "application/json"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("sku", ["ABC 123", "ABC/123", "<b>1</b>", "sku;drop", "x" * 51, "", "   "])
def test_sku_character_whitelist(client, sku):
    response = client.post("/api/products", json={"sku": sku, "name": "n", "unit_price": 1})
    assert response.status_code == 400
    assert "sku" in response.get_json()["details"]


@pytest.mark.parametrize("raw", ["Infinity", "NaN", "1e308", "-0.0001", '"1e3"', '"0x10"', '"Infinity"',
                                 '"1,000"', '"$5"', "true", '"12.5.1"'])
def test_prices_reject_non_finite_or_odd_numeric_encodings(client, raw):
    payload = '{"sku": "P-1", "name": "n", "unit_price": %s}' % raw
    response = client.post("/api/products", data=payload, content_type="application/json")
    assert response.status_code == 400, response.get_json()
    assert "unit_price" in response.get_json()["details"]


@pytest.mark.parametrize("raw,expected", [('"12"', 12.0), ('"12.50"', 12.5), ('".5"', 0.5), ("19.999", 20.0), ("0", 0.0)])
def test_prices_accept_plain_numbers_and_numeric_strings(client, raw, expected):
    payload = '{"sku": "P-%s", "name": "n", "unit_price": %s}' % (abs(hash(raw)) % 10000, raw)
    response = client.post("/api/products", data=payload, content_type="application/json")
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["unit_price"] == expected


@pytest.mark.parametrize("path", ["/api/products/0", "/api/products/-1", "/api/products/abc",
                                  "/api/products/99999999999999999999", "/api/products/1e3"])
def test_bad_ids_in_urls_are_404_not_500(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert response.mimetype == "application/json"


def test_cors_only_allows_configured_origins(client):
    allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    blocked = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in blocked.headers


def test_stock_endpoints_require_integer_product_ids(client, product):
    for bad in [1.5, None, True, [1], {"id": 1}, "1 OR 1=1", "abc", ""]:
        response = client.post("/api/stock/in", json={"product_id": bad, "quantity": 1})
        assert response.status_code == 400, bad
        assert "product_id" in response.get_json()["details"]
    # Digit strings are accepted (HTML inputs send strings) - same as everywhere else.
    assert client.post("/api/stock/in", json={"product_id": str(product["id"]), "quantity": 1}).status_code == 201
