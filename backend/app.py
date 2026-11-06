"""
Auspify IMS - Flask backend entry point.

Run it (from the backend/ folder, with the virtualenv activated):
    python app.py

Structure:
    app.py          create_app() factory - wires everything together
    config.py       settings (database path, CORS origins, limits)
    database.py     SQLite connection handling, transactions, first-run setup
    schema.sql      tables, constraints and indexes
    seed.py         sample data
    errors.py       error types -> JSON responses
    validation.py   input validation helpers
    models/         database layer (all SQL)
    routes/         HTTP layer (Flask blueprints)
"""

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.routing import IntegerConverter

import database
from config import Config
from errors import register_error_handlers
from routes import categories, products, reports, stock, suppliers


class IdConverter(IntegerConverter):
    """
    URL converter for record ids, used as <id:product_id> in routes.

    Flask's built-in <int:> accepts numbers of any size, but SQLite can only
    store 64-bit integers and the driver raises an error for anything larger.
    Limiting ids to 1 .. 2^63-1 means out-of-range values simply do not match
    the route and get a clean 404 instead of a server error.
    """

    def __init__(self, map, **kwargs):
        super().__init__(map, min=1, max=2**63 - 1)


def create_app(test_config=None):
    """
    Application factory.

    `test_config` lets tests override settings (e.g. point DATABASE at a
    temporary file and disable AUTO_SEED) without touching environment
    variables.
    """
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    # <id:...> in route URLs = positive 64-bit integer (see IdConverter).
    app.url_map.converters["id"] = IdConverter

    # CORS: only the origins listed in config may call /api/* from a browser.
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    # Database: create tables on first run, seed if empty, close per request.
    database.init_app(app)

    # Consistent JSON errors for every failure (400/404/405/409/413/500).
    register_error_handlers(app)

    # Resource routes.
    app.register_blueprint(categories.bp)
    app.register_blueprint(suppliers.bp)
    app.register_blueprint(products.bp)
    app.register_blueprint(stock.bp)
    app.register_blueprint(reports.bp)

    @app.get("/api/health")
    def health():
        """Liveness check: returns a small JSON payload if the server is up."""
        return jsonify({"status": "ok", "service": "auspify-ims-backend"})

    @app.after_request
    def set_security_headers(response):
        """
        Defensive headers for every response:
          * nosniff      - browsers must not guess content types
          * DENY         - API responses can never be framed by another site
          * no-referrer  - do not leak our URLs to third parties
          * no-store     - inventory data must not linger in shared caches
        """
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


if __name__ == "__main__":
    # host="0.0.0.0" listens on all network interfaces so the server is
    # reachable from containers / remote previews, not just this machine.
    # debug=True gives auto-reload on code changes (our error handler still
    # hides stack traces from API clients).
    create_app().run(host="0.0.0.0", port=5000, debug=True)
