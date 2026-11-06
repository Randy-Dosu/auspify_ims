"""Search, filter, sort and pagination: each option alone and in combination."""

import itertools

import pytest

from tests.conftest import make_product


@pytest.fixture
def catalogue(client):
    """
    Six products across two categories / two suppliers with known attributes.

      sku      name                 cat   sup   price   qty  reorder  status
      ELEC-1   Wireless Mouse       E     A      85      59    15     in_stock
      ELEC-2   USB-C Cable          E     A      35.5    0     25     out
      ELEC-3   Keyboard             E     B     220      2     10     low
      OFF-1    A4 Paper             O     B      42      72    40     in_stock
      OFF-2    Blue Pens            O     A      55     20     20     low
      OFF-3    mouse pad (100%)     O     -       9.99   5      0     in_stock
    """
    e = client.post("/api/categories", json={"name": "Electronics"}).get_json()["id"]
    o = client.post("/api/categories", json={"name": "Office"}).get_json()["id"]
    a = client.post("/api/suppliers", json={"name": "Supplier A"}).get_json()["id"]
    b = client.post("/api/suppliers", json={"name": "Supplier B"}).get_json()["id"]
    rows = [
        ("ELEC-1", "Wireless Mouse", e, a, 85, 59, 15),
        ("ELEC-2", "USB-C Cable", e, a, 35.5, 0, 25),
        ("ELEC-3", "Keyboard", e, b, 220, 2, 10),
        ("OFF-1", "A4 Paper", o, b, 42, 72, 40),
        ("OFF-2", "Blue Pens", o, a, 55, 20, 20),
        ("OFF-3", "mouse pad (100%)", o, None, 9.99, 5, 0),
    ]
    for sku, name, cat, sup, price, qty, reorder in rows:
        make_product(client, sku=sku, name=name, category_id=cat, supplier_id=sup,
                     unit_price=price, quantity_in_stock=qty, reorder_level=reorder)
    return {"electronics": e, "office": o, "supplier_a": a, "supplier_b": b}


def skus(client, query=""):
    response = client.get(f"/api/products?{query}")
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    return [p["sku"] for p in body["items"]], body


# --------------------------------------------------------------------------- #
# Each filter on its own
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "term,expected",
    [
        ("mouse", {"ELEC-1", "OFF-3"}),          # case-insensitive, name
        ("MOUSE", {"ELEC-1", "OFF-3"}),
        ("elec-", {"ELEC-1", "ELEC-2", "ELEC-3"}),  # partial SKU
        ("usb-c cable", {"ELEC-2"}),             # phrase with space and dash
        ("100%", {"OFF-3"}),                     # literal percent sign
        ("%", {"OFF-3"}),                        # bare wildcard is escaped
        ("_", set()),                            # bare underscore is escaped
        ("nothing-here", set()),
    ],
)
def test_search_is_partial_case_insensitive_and_literal(client, catalogue, term, expected):
    found, body = skus(client, f"search={term}")
    assert set(found) == expected
    assert body["total"] == len(expected)


def test_filter_by_category(client, catalogue):
    assert set(skus(client, f"category={catalogue['office']}")[0]) == {"OFF-1", "OFF-2", "OFF-3"}


def test_filter_by_supplier(client, catalogue):
    assert set(skus(client, f"supplier={catalogue['supplier_b']}")[0]) == {"ELEC-3", "OFF-1"}


@pytest.mark.parametrize("status,expected", [
    ("in_stock", {"ELEC-1", "OFF-1", "OFF-3"}),
    ("low", {"ELEC-3", "OFF-2"}),
    ("out", {"ELEC-2"}),
])
def test_filter_by_stock_status(client, catalogue, status, expected):
    assert set(skus(client, f"stock_status={status}")[0]) == expected


def test_filter_by_price_range_is_inclusive(client, catalogue):
    assert set(skus(client, "min_price=55")[0]) == {"ELEC-1", "ELEC-3", "OFF-2"}
    assert set(skus(client, "max_price=42")[0]) == {"ELEC-2", "OFF-1", "OFF-3"}
    assert set(skus(client, "min_price=35.5&max_price=55")[0]) == {"ELEC-2", "OFF-1", "OFF-2"}
    assert skus(client, "min_price=1000")[0] == []


# --------------------------------------------------------------------------- #
# Combinations
# --------------------------------------------------------------------------- #


def test_every_pair_of_filters_narrows_results_consistently(client, catalogue):
    """
    For every pair of filters, the combined result must equal the intersection
    of the individual results (AND semantics) - the general rule behind all
    filter combinations.
    """
    filters = {
        "search": "search=e",
        "category": f"category={catalogue['electronics']}",
        "supplier": f"supplier={catalogue['supplier_a']}",
        "stock_status": "stock_status=in_stock",
        "min_price": "min_price=40",
        "max_price": "max_price=90",
    }
    single = {name: set(skus(client, q)[0]) for name, q in filters.items()}
    for (n1, q1), (n2, q2) in itertools.combinations(filters.items(), 2):
        combined = set(skus(client, f"{q1}&{q2}")[0])
        assert combined == single[n1] & single[n2], (n1, n2)


def test_all_filters_together(client, catalogue):
    query = (f"search=mouse&category={catalogue['electronics']}&supplier={catalogue['supplier_a']}"
             "&stock_status=in_stock&min_price=50&max_price=100")
    assert skus(client, query)[0] == ["ELEC-1"]
    assert skus(client, query + "&page=1&per_page=1&sort=sku&order=desc")[0] == ["ELEC-1"]


# --------------------------------------------------------------------------- #
# Sorting & pagination
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("column,key", [
    ("unit_price", "unit_price"),
    ("quantity_in_stock", "quantity_in_stock"),
    ("reorder_level", "reorder_level"),
    ("sku", "sku"),
])
def test_sorting_both_directions(client, catalogue, column, key):
    asc = client.get(f"/api/products?sort={column}&order=asc").get_json()["items"]
    desc = client.get(f"/api/products?sort={column}&order=desc").get_json()["items"]
    normalise = (lambda v: v.lower()) if isinstance(asc[0][key], str) else (lambda v: v)
    assert [normalise(p[key]) for p in asc] == sorted(normalise(p[key]) for p in asc)
    assert [normalise(p[key]) for p in desc] == sorted((normalise(p[key]) for p in desc), reverse=True)


def test_sort_by_name_is_case_insensitive(client, catalogue):
    names = [p["name"] for p in client.get("/api/products?sort=name").get_json()["items"]]
    assert names == sorted(names, key=str.lower)
    assert names.index("mouse pad (100%)") < names.index("USB-C Cable")  # lower-case m before upper-case U


def test_sort_by_joined_columns(client, catalogue):
    by_cat = [p["category_name"] for p in client.get("/api/products?sort=category&order=desc").get_json()["items"]]
    assert by_cat[0] == "Office" and by_cat[-1] == "Electronics"
    by_sup = [p["supplier_name"] for p in client.get("/api/products?sort=supplier").get_json()["items"]]
    assert by_sup[0] is None and by_sup[-1] == "Supplier B"  # NULLs first in ascending order


def test_pagination_counts_and_pages(client, catalogue):
    page1 = client.get("/api/products?per_page=4&sort=sku").get_json()
    page2 = client.get("/api/products?per_page=4&page=2&sort=sku").get_json()
    page3 = client.get("/api/products?per_page=4&page=3&sort=sku").get_json()
    assert (page1["total"], page1["total_pages"], page1["page"], page1["per_page"]) == (6, 2, 1, 4)
    assert len(page1["items"]) == 4 and len(page2["items"]) == 2 and page3["items"] == []
    assert page3["total"] == 6
    collected = [p["sku"] for p in page1["items"] + page2["items"]]
    assert collected == sorted(collected) and len(set(collected)) == 6


def test_pagination_respects_filters(client, catalogue):
    body = client.get(f"/api/products?category={catalogue['office']}&per_page=2").get_json()
    assert body["total"] == 3 and body["total_pages"] == 2 and len(body["items"]) == 2


def test_default_response_shape(client, catalogue):
    body = client.get("/api/products").get_json()
    assert set(body) == {"items", "total", "page", "per_page", "total_pages", "sort", "order"}
    assert (body["page"], body["per_page"], body["sort"], body["order"]) == (1, 20, "name", "asc")


def test_empty_database_list_is_well_formed(client):
    body = client.get("/api/products?search=x&page=5").get_json()
    assert body == {"items": [], "total": 0, "page": 5, "per_page": 20, "total_pages": 1, "sort": "name", "order": "asc"}


# --------------------------------------------------------------------------- #
# Invalid parameters are rejected, never guessed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("query,field", [
    ("page=0", "page"), ("page=-1", "page"), ("page=abc", "page"), ("page=1.5", "page"),
    ("page=99999999999999999999", "page"),
    ("per_page=0", "per_page"), ("per_page=101", "per_page"), ("per_page=ten", "per_page"),
    ("sort=id", "sort"), ("sort=p.name;DROP TABLE products;--", "sort"),
    ("order=up", "order"),
    ("stock_status=plenty", "stock_status"),
    ("min_price=abc", "min_price"), ("min_price=-1", "min_price"), ("max_price=NaN", "max_price"),
    ("min_price=10&max_price=5", "min_price"),
    ("category=abc", "category"), ("category=0", "category"), ("category=1 OR 1=1", "category"),
    ("supplier=-3", "supplier"),
    ("search=" + "x" * 101, "search"),
])
def test_invalid_query_parameters_return_400(client, catalogue, query, field):
    response = client.get(f"/api/products?{query}")
    assert response.status_code == 400, response.get_json()
    assert field in response.get_json()["details"]


@pytest.mark.parametrize("payload", ["' OR 1=1 --", "%' OR '1'='1", "\\'; DROP TABLE products; --",
                                     "' UNION SELECT 1,2,3 --", "<script>alert(1)</script>"])
def test_injection_payloads_are_plain_search_text(client, catalogue, payload):
    response = client.get("/api/products", query_string={"search": payload})
    assert response.status_code == 200
    assert response.get_json()["total"] == 0
    assert client.get("/api/products").get_json()["total"] == 6  # table intact
