-- =============================================================================
-- Auspify IMS database schema (SQLite)
--
-- Every statement uses IF NOT EXISTS so this file can be run safely on every
-- start-up: it creates the tables the first time and is a no-op afterwards.
--
-- NOTE: foreign-key enforcement is a per-connection setting in SQLite
-- (PRAGMA foreign_keys = ON). It is switched on in database.py every time a
-- connection is opened.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- categories: a product belongs to at most one category.
-- COLLATE NOCASE makes the UNIQUE constraint case-insensitive, so
-- "Electronics" and "electronics" cannot both exist.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    CHECK (length(trim(name)) > 0)
);

-- ---------------------------------------------------------------------------
-- suppliers: who we buy a product from.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS suppliers (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT    NOT NULL,
    email TEXT,
    phone TEXT,
    CHECK (length(trim(name)) > 0)
);

-- ---------------------------------------------------------------------------
-- products: the items we keep in stock.
--   * sku is the business identifier and must be unique (case-insensitive).
--   * CHECK constraints are the database's own guarantee that price and
--     quantities can never be negative, even if application code has a bug.
--   * ON DELETE RESTRICT: a category/supplier that is still referenced by a
--     product cannot be deleted (the API turns this into a clear 409 error).
--   * Timestamps are stored as ISO-8601 UTC text, e.g. 2026-11-06T09:58:45Z.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    sku               TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    name              TEXT    NOT NULL,
    description       TEXT,
    category_id       INTEGER REFERENCES categories(id) ON DELETE RESTRICT,
    supplier_id       INTEGER REFERENCES suppliers(id)  ON DELETE RESTRICT,
    unit_price        REAL    NOT NULL DEFAULT 0  CHECK (unit_price >= 0),
    quantity_in_stock INTEGER NOT NULL DEFAULT 0  CHECK (quantity_in_stock >= 0),
    reorder_level     INTEGER NOT NULL DEFAULT 10 CHECK (reorder_level >= 0),
    created_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (length(trim(sku))  > 0),
    CHECK (length(trim(name)) > 0)
);

-- ---------------------------------------------------------------------------
-- stock_transactions: the audit log. Every change to quantity_in_stock
-- must be accompanied by exactly one row here.
--   * IN          quantity > 0, stock received
--   * OUT         quantity > 0, stock sold/used
--   * ADJUSTMENT  signed delta (+5 or -3) from a stock count correction
-- ON DELETE CASCADE: deleting a product also removes its history.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_transactions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    type       TEXT    NOT NULL CHECK (type IN ('IN', 'OUT', 'ADJUSTMENT')),
    quantity   INTEGER NOT NULL,
    reason     TEXT,
    note       TEXT,
    created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    -- IN/OUT must be positive; an adjustment can be + or - but never zero.
    CHECK (
        (type IN ('IN', 'OUT') AND quantity > 0)
        OR (type = 'ADJUSTMENT' AND quantity <> 0)
    )
);

-- ---------------------------------------------------------------------------
-- Indexes for the columns we search, filter and join on most.
-- (products.sku already has an automatic unique index from its UNIQUE
--  constraint, so a second index on it is not needed.)
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_products_name        ON products(name);
CREATE INDEX IF NOT EXISTS idx_products_category_id ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_supplier_id ON products(supplier_id);
CREATE INDEX IF NOT EXISTS idx_transactions_product ON stock_transactions(product_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created ON stock_transactions(created_at);
