"""
Data integrity audit.

Reads the SQLite database directly (no Flask) and checks the invariants the
application promises to keep. Run it any time - after a crash, before a
backup, as a nightly cron job:

    cd backend
    source .venv/bin/activate
    python audit.py                      # audits instance/inventory.db
    python audit.py path/to/other.db     # audits a specific file

Exit code 0 = every check passed, 1 = at least one discrepancy, 2 = could not
open the database. The checks:

  1. Stock ledger   - for every product, quantity_in_stock must equal
                      SUM(IN) - SUM(OUT) + SUM(ADJUSTMENT) of its transactions.
  2. Valuation      - the summary report's total_value must equal
                      SUM(quantity_in_stock * unit_price) over all products.
  3. Orphans        - every products.category_id / supplier_id and every
                      stock_transactions.product_id must point at a real row.
  4. Negatives      - no negative quantities, prices, reorder levels or
                      transaction quantities; every type is IN/OUT/ADJUSTMENT.
  5. Uniqueness     - no duplicate SKUs or category names (even by case).
  6. File integrity - SQLite's own PRAGMA integrity_check / foreign_key_check.
"""

import os
import sqlite3
import sys

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance", "inventory.db")

# Set to False (or pass --quiet) to only print failures.
VERBOSE = "--quiet" not in sys.argv


class Audit:
    """Collects check results and prints a short report."""

    def __init__(self, conn):
        self.conn = conn
        self.failures = []   # (check name, list of human-readable problems)
        self.passed = []

    def record(self, name, problems, detail=""):
        if problems:
            self.failures.append((name, problems))
            print(f"FAIL  {name}: {len(problems)} problem(s)")
            for p in problems[:20]:
                print(f"        - {p}")
            if len(problems) > 20:
                print(f"        ... and {len(problems) - 20} more")
        else:
            self.passed.append(name)
            if VERBOSE:
                print(f"PASS  {name}{(' (' + detail + ')') if detail else ''}")

    # ------------------------------------------------------------------ #
    # 1. Ledger: quantity == sum(IN) - sum(OUT) + sum(ADJUSTMENT)
    # ------------------------------------------------------------------ #
    def check_ledger(self):
        rows = self.conn.execute(
            """
            SELECT p.id, p.sku, p.quantity_in_stock,
                   COALESCE(SUM(CASE t.type WHEN 'IN'         THEN  t.quantity
                                            WHEN 'OUT'        THEN -t.quantity
                                            WHEN 'ADJUSTMENT' THEN  t.quantity END), 0) AS ledger
            FROM products p
            LEFT JOIN stock_transactions t ON t.product_id = p.id
            GROUP BY p.id
            """
        ).fetchall()
        problems = [
            f"{r['sku']} (id {r['id']}): quantity_in_stock={r['quantity_in_stock']} but ledger sums to {r['ledger']}"
            for r in rows if r["quantity_in_stock"] != r["ledger"]
        ]
        self.record("Stock ledger matches quantity_in_stock", problems, f"{len(rows)} products checked")

    # ------------------------------------------------------------------ #
    # 2. Valuation: report total == sum(qty * price)
    # ------------------------------------------------------------------ #
    def check_valuation(self):
        rows = self.conn.execute("SELECT sku, quantity_in_stock, unit_price FROM products").fetchall()
        # Computed in Python, independently of the SQL used by the report.
        expected = round(sum(r["quantity_in_stock"] * r["unit_price"] for r in rows), 2)
        reported = self.conn.execute(
            "SELECT ROUND(COALESCE(SUM(quantity_in_stock * unit_price), 0), 2) FROM products"
        ).fetchone()[0]
        problems = []
        if abs(expected - reported) > 0.005:
            problems.append(f"report says {reported} but products sum to {expected}")
        self.record("Inventory value equals sum(quantity x unit_price)", problems, f"total {reported:,.2f}")

    # ------------------------------------------------------------------ #
    # 3. Orphaned foreign keys
    # ------------------------------------------------------------------ #
    def check_orphans(self):
        problems = []
        for sql, label in (
            ("SELECT p.id, p.sku FROM products p LEFT JOIN categories c ON c.id = p.category_id "
             "WHERE p.category_id IS NOT NULL AND c.id IS NULL", "product {sku} (id {id}) has a missing category"),
            ("SELECT p.id, p.sku FROM products p LEFT JOIN suppliers s ON s.id = p.supplier_id "
             "WHERE p.supplier_id IS NOT NULL AND s.id IS NULL", "product {sku} (id {id}) has a missing supplier"),
            ("SELECT t.id, t.product_id AS sku FROM stock_transactions t LEFT JOIN products p ON p.id = t.product_id "
             "WHERE p.id IS NULL", "transaction {id} points at missing product {sku}"),
        ):
            for r in self.conn.execute(sql).fetchall():
                problems.append(label.format(id=r["id"], sku=r["sku"]))
        self.record("No orphaned foreign keys", problems)

    # ------------------------------------------------------------------ #
    # 4. Negative or invalid values
    # ------------------------------------------------------------------ #
    def check_negatives(self):
        problems = []
        for r in self.conn.execute(
            "SELECT id, sku, quantity_in_stock, unit_price, reorder_level FROM products "
            "WHERE quantity_in_stock < 0 OR unit_price < 0 OR reorder_level < 0"
        ):
            problems.append(f"product {r['sku']} (id {r['id']}): qty={r['quantity_in_stock']} "
                            f"price={r['unit_price']} reorder={r['reorder_level']}")
        for r in self.conn.execute(
            "SELECT id, type, quantity FROM stock_transactions "
            "WHERE type NOT IN ('IN', 'OUT', 'ADJUSTMENT') OR quantity = 0 "
            "   OR (type IN ('IN', 'OUT') AND quantity <= 0)"
        ):
            problems.append(f"transaction {r['id']}: type={r['type']} quantity={r['quantity']}")
        self.record("No negative stock, prices or invalid transactions", problems)

    # ------------------------------------------------------------------ #
    # 5. Uniqueness (case-insensitive, so 'abc-1' and 'ABC-1' both count)
    # ------------------------------------------------------------------ #
    def check_uniqueness(self):
        problems = []
        for table, column in (("products", "sku"), ("categories", "name")):
            for r in self.conn.execute(
                f"SELECT {column} AS value, COUNT(*) AS n FROM {table} "
                f"GROUP BY {column} COLLATE NOCASE HAVING n > 1"
            ):
                problems.append(f"{table}.{column} '{r['value']}' appears {r['n']} times")
        self.record("SKUs and category names are unique", problems)

    # ------------------------------------------------------------------ #
    # 6. SQLite's own consistency checks
    # ------------------------------------------------------------------ #
    def check_sqlite(self):
        problems = []
        result = self.conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            problems.append(f"integrity_check: {result}")
        for r in self.conn.execute("PRAGMA foreign_key_check").fetchall():
            problems.append(f"foreign_key_check: table {r[0]} row {r[1]} -> {r[2]}")
        self.record("SQLite integrity_check / foreign_key_check", problems)

    def run(self):
        self.check_ledger()
        self.check_valuation()
        self.check_orphans()
        self.check_negatives()
        self.check_uniqueness()
        self.check_sqlite()
        return not self.failures


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    path = args[0] if args else DEFAULT_DB
    if not os.path.exists(path):
        print(f"Database not found: {path}")
        return 2

    # mode=ro: the audit can never modify the data it is checking.
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("categories", "suppliers", "products", "stock_transactions")}
    except sqlite3.DatabaseError as exc:
        print(f"Cannot read database {path}: {exc}")
        return 2

    print(f"Auditing {path}")
    print("  " + ", ".join(f"{n} {t}" for t, n in counts.items()))
    audit = Audit(conn)
    ok = audit.run()
    conn.close()

    print()
    if ok:
        print(f"ALL CHECKS PASSED ({len(audit.passed)}/{len(audit.passed)})")
        return 0
    print(f"{len(audit.failures)} CHECK(S) FAILED, {len(audit.passed)} passed")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
