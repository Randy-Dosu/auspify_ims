"""
Database layer: opening connections, transactions and first-run setup.

All SQL that *reads or writes business data* lives in the models/ package.
This module only knows how to talk to SQLite safely.
"""

import os
import sqlite3
from contextlib import contextmanager

from flask import current_app, g

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def connect(db_path):
    """
    Open a new SQLite connection with the settings this project relies on.

    * isolation_level=None  -> "autocommit" mode: single statements commit on
      their own and multi-statement work uses the explicit transaction()
      helper below. Nothing is left half-done by accident.
    * row_factory=Row       -> rows behave like dicts (row["name"]).
    * foreign_keys=ON       -> SQLite only enforces FOREIGN KEY constraints when
      this pragma is on, and it must be set for every connection.
    * busy_timeout          -> if two requests write at the same time, the
      second one waits (up to 5 s) instead of failing with "database is locked".
    * journal_mode=WAL      -> readers do not block writers and vice versa.
    """
    directory = os.path.dirname(db_path)
    if directory and db_path != ":memory:":
        os.makedirs(directory, exist_ok=True)

    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db():
    """
    Return the connection for the current request, opening it on first use.

    Flask's `g` object lives for exactly one request, so each request gets its
    own connection and close_db() releases it when the request ends.
    """
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exception=None):
    """Close the request's connection (registered as a teardown handler)."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def transaction(conn):
    """
    Run several statements as ONE atomic unit:

        with transaction(conn):
            conn.execute(...)   # update product quantity
            conn.execute(...)   # insert stock_transactions row

    Either both statements are saved (COMMIT) or neither is (ROLLBACK).
    BEGIN IMMEDIATE takes the write lock straight away, so two concurrent
    stock operations on the same product are processed one after the other
    instead of interleaving.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def init_db(app):
    """
    Create the schema if needed and, when the database is empty and
    AUTO_SEED is enabled, load the sample data. Safe to call on every start.
    """
    conn = connect(app.config["DATABASE"])
    try:
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            conn.executescript(f.read())

        if app.config.get("AUTO_SEED"):
            product_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            if product_count == 0:
                # Imported here to avoid a circular import at module load time.
                from seed import seed_database

                seed_database(conn)
                app.logger.info("Database was empty - sample data inserted.")
    finally:
        conn.close()


def init_app(app):
    """Hook the database layer into the Flask app."""
    app.teardown_appcontext(close_db)
    init_db(app)
