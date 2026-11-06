"""
Sample data for development and demos.

seed_database(conn) is called automatically by database.init_db() when the
database is empty. You can also run this file directly:

    python seed.py            # seed only if the database is empty
    python seed.py --reset    # wipe all rows and seed again

The stock history is generated deterministically (fixed random seed) so every
fresh database looks the same. Quantities are derived FROM the generated
transactions, so the audit rule "quantity_in_stock == sum of transactions"
holds from day one.
"""

import random
import sys
from datetime import datetime, timedelta, timezone

CATEGORIES = [
    "Electronics",
    "Office Supplies",
    "Furniture",
    "Cleaning Supplies",
    "Beverages",
    "Packaging",
]

SUPPLIERS = [
    ("Accra Tech Distributors", "sales@accratech.example.com", "+233 30 222 1100"),
    ("Kumasi Office Mart", "orders@kom.example.com", "+233 32 204 5566"),
    ("Tema Industrial Supplies", "info@temaindustrial.example.com", "+233 30 320 7788"),
    ("Volta Fresh Beverages", "hello@voltafresh.example.com", "+233 24 555 0199"),
]

# (sku, name, description, category, supplier, unit_price, reorder_level)
PRODUCTS = [
    ("ELEC-001", "Wireless Mouse", "2.4 GHz optical mouse with USB receiver", "Electronics", "Accra Tech Distributors", 85.00, 15),
    ("ELEC-002", "USB-C Charging Cable 1m", "Braided USB-C to USB-C cable, 60 W", "Electronics", "Accra Tech Distributors", 35.50, 25),
    ("ELEC-003", "Bluetooth Keyboard", "Slim rechargeable keyboard", "Electronics", "Accra Tech Distributors", 220.00, 10),
    ("ELEC-004", "24-inch LED Monitor", "Full HD IPS display, HDMI + VGA", "Electronics", "Accra Tech Distributors", 1450.00, 5),
    ("ELEC-005", "Power Bank 10000mAh", "Dual USB output power bank", "Electronics", "Accra Tech Distributors", 160.00, 12),
    ("OFF-001", "A4 Copy Paper (Ream)", "80 gsm, 500 sheets", "Office Supplies", "Kumasi Office Mart", 42.00, 40),
    ("OFF-002", "Ballpoint Pens (Box of 50)", "Blue ink, medium point", "Office Supplies", "Kumasi Office Mart", 55.00, 20),
    ("OFF-003", "Stapler Heavy Duty", "Staples up to 100 sheets", "Office Supplies", "Kumasi Office Mart", 98.75, 8),
    ("OFF-004", "Sticky Notes (12 pads)", "76 x 76 mm, assorted colours", "Office Supplies", "Kumasi Office Mart", 28.00, 15),
    ("FURN-001", "Ergonomic Office Chair", "Mesh back, adjustable height and arms", "Furniture", "Tema Industrial Supplies", 1250.00, 4),
    ("FURN-002", "Standing Desk 120cm", "Electric height-adjustable desk", "Furniture", "Tema Industrial Supplies", 2890.00, 3),
    ("FURN-003", "4-Drawer Filing Cabinet", "Steel cabinet with lock", "Furniture", "Tema Industrial Supplies", 980.00, 3),
    ("CLN-001", "Multi-Surface Cleaner 5L", "Concentrated, lemon scented", "Cleaning Supplies", "Tema Industrial Supplies", 65.00, 10),
    ("CLN-002", "Nitrile Gloves (Box of 100)", "Powder-free, size M", "Cleaning Supplies", "Tema Industrial Supplies", 72.00, 20),
    ("CLN-003", "Paper Towel Rolls (6 pack)", "2-ply, 100 sheets per roll", "Cleaning Supplies", "Tema Industrial Supplies", 48.50, 15),
    ("BEV-001", "Bottled Water 500ml (24 pack)", "Still mineral water", "Beverages", "Volta Fresh Beverages", 36.00, 30),
    ("BEV-002", "Ground Coffee 1kg", "Medium roast, Arabica", "Beverages", "Volta Fresh Beverages", 145.00, 10),
    ("BEV-003", "Green Tea (100 bags)", "Individually wrapped tea bags", "Beverages", "Volta Fresh Beverages", 58.00, 10),
    ("BEV-004", "Fruit Juice 1L (12 pack)", "Mixed tropical fruit juice", "Beverages", "Volta Fresh Beverages", 96.00, 12),
    ("PKG-001", "Cardboard Boxes Medium (25)", "40 x 30 x 30 cm, double wall", "Packaging", "Tema Industrial Supplies", 120.00, 10),
    ("PKG-002", "Packing Tape (36 rolls)", "48 mm x 66 m clear tape", "Packaging", "Tema Industrial Supplies", 210.00, 6),
    ("PKG-003", "Bubble Wrap Roll 50m", "Small bubble, 50 cm wide", "Packaging", "Tema Industrial Supplies", 88.00, 5),
]

# Products that should end LOW (0 < qty <= reorder_level) or OUT (qty == 0)
# so the dashboard and badges have something to show.
FORCE_LOW = {"ELEC-004", "OFF-003", "FURN-002", "BEV-002"}
FORCE_OUT = {"ELEC-003", "PKG-003"}


def _iso(dt):
    """Format a datetime the same way the schema's default does."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_database(conn):
    """Insert all sample data using the given connection."""
    rng = random.Random(42)  # fixed seed -> reproducible data
    now = datetime.now(timezone.utc).replace(microsecond=0)

    # --- categories & suppliers ------------------------------------------
    category_ids = {}
    for name in CATEGORIES:
        cur = conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        category_ids[name] = cur.lastrowid

    supplier_ids = {}
    for name, email, phone in SUPPLIERS:
        cur = conn.execute(
            "INSERT INTO suppliers (name, email, phone) VALUES (?, ?, ?)",
            (name, email, phone),
        )
        supplier_ids[name] = cur.lastrowid

    # --- products + generated stock history --------------------------------
    for sku, name, desc, cat, sup, price, reorder in PRODUCTS:
        created = now - timedelta(days=45, hours=rng.randint(0, 8))
        cur = conn.execute(
            """
            INSERT INTO products
                (sku, name, description, category_id, supplier_id, unit_price,
                 quantity_in_stock, reorder_level, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (sku, name, desc, category_ids[cat], supplier_ids[sup], price,
             reorder, _iso(created), _iso(created)),
        )
        product_id = cur.lastrowid

        # Initial stock received when the product was created.
        initial = rng.randint(max(reorder * 2, 10), reorder * 5 + 20)
        movements = [("IN", initial, "Initial stock", None, created)]
        quantity = initial

        # A few weeks of realistic activity: mostly sales, some restocks,
        # the occasional stock-count correction.
        for _ in range(rng.randint(3, 8)):
            when = created + timedelta(
                days=rng.randint(1, 44), hours=rng.randint(8, 18), minutes=rng.randint(0, 59)
            )
            if when > now:
                continue
            roll = rng.random()
            if roll < 0.65 and quantity > 0:
                qty = rng.randint(1, max(1, quantity // 3))
                movements.append(("OUT", qty, "Sale", None, when))
                quantity -= qty
            elif roll < 0.9:
                qty = rng.randint(5, reorder * 2 + 5)
                movements.append(("IN", qty, "Purchase order", None, when))
                quantity += qty
            else:
                delta = rng.choice([-2, -1, 1, 2])
                if quantity + delta >= 0:
                    movements.append(("ADJUSTMENT", delta, "Stock count correction",
                                      "Physical count differed from system", when))
                    quantity += delta

        # Force a few products into the LOW / OUT zone for demo purposes.
        if sku in FORCE_OUT and quantity > 0:
            movements.append(("OUT", quantity, "Sale", "Bulk order", now - timedelta(days=1)))
            quantity = 0
        elif sku in FORCE_LOW and quantity > reorder:
            take = quantity - max(1, reorder // 2)
            movements.append(("OUT", take, "Sale", "Bulk order", now - timedelta(days=2)))
            quantity -= take

        movements.sort(key=lambda m: m[4])
        for mtype, qty, reason, note, when in movements:
            conn.execute(
                """
                INSERT INTO stock_transactions (product_id, type, quantity, reason, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (product_id, mtype, qty, reason, note, _iso(when)),
            )

        last_change = movements[-1][4]
        conn.execute(
            "UPDATE products SET quantity_in_stock = ?, updated_at = ? WHERE id = ?",
            (quantity, _iso(last_change), product_id),
        )


def reset_database(conn):
    """Delete every row (children first, to respect foreign keys)."""
    conn.execute("DELETE FROM stock_transactions")
    conn.execute("DELETE FROM products")
    conn.execute("DELETE FROM suppliers")
    conn.execute("DELETE FROM categories")
    # Restart AUTOINCREMENT counters so ids begin at 1 again.
    conn.execute("DELETE FROM sqlite_sequence")


if __name__ == "__main__":
    # Allow running as a standalone script against the configured database.
    from config import Config
    from database import SCHEMA_PATH, connect, transaction

    connection = connect(Config.DATABASE)
    with open(SCHEMA_PATH, encoding="utf-8") as schema_file:
        connection.executescript(schema_file.read())

    with transaction(connection):
        if "--reset" in sys.argv:
            reset_database(connection)
        existing = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if existing:
            print(f"Database already has {existing} products - nothing to do "
                  f"(use --reset to start over).")
        else:
            seed_database(connection)
            print("Sample data inserted into", Config.DATABASE)
    connection.close()
