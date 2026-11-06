"""
Shared pytest fixtures.

Every test gets a brand-new SQLite database in a temporary directory with the
schema created and NO seed data, so tests are independent and deterministic.
"""

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    """A Flask app bound to an empty temporary database."""
    application = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.db"),
        "AUTO_SEED": False,
    })
    yield application


@pytest.fixture
def client(app):
    """HTTP test client (no running server needed)."""
    return app.test_client()


@pytest.fixture
def category(client):
    return client.post("/api/categories", json={"name": "Electronics"}).get_json()


@pytest.fixture
def supplier(client):
    return client.post(
        "/api/suppliers",
        json={"name": "Accra Tech", "email": "sales@accratech.example.com", "phone": "+233 30 222 1100"},
    ).get_json()


def make_product(client, **overrides):
    """Create a product with sensible defaults; override any field."""
    payload = {
        "sku": "TEST-001",
        "name": "Test Product",
        "unit_price": 10.0,
        "quantity_in_stock": 0,
        "reorder_level": 5,
    }
    payload.update(overrides)
    response = client.post("/api/products", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


@pytest.fixture
def product(client, category, supplier):
    """A product with 20 units in stock, reorder level 5."""
    return make_product(
        client,
        category_id=category["id"],
        supplier_id=supplier["id"],
        quantity_in_stock=20,
        unit_price=12.5,
    )
