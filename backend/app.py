"""
Auspify IMS - Flask backend entry point.

Step 0 scope: a minimal Flask application exposing a single health-check
endpoint so we can prove that
  1. the backend runs, and
  2. the React frontend can reach it.

Run it (from the backend/ folder, with the virtualenv activated):
    python app.py
"""

from flask import Flask, jsonify
from flask_cors import CORS


def create_app():
    """
    Application factory.

    Building the app inside a function (instead of at import time) is a
    common Flask pattern: it keeps configuration in one place and makes the
    app easy to create on demand (for example, from other scripts).
    """
    app = Flask(__name__)

    # Enable CORS for every route under /api/*.
    # The React dev server runs on a different port (5173) than Flask (5000),
    # so the browser treats them as different "origins". CORS headers tell
    # the browser it is allowed to call this API from the React app.
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    @app.get("/api/health")
    def health():
        """Liveness check: returns a small JSON payload if the server is up."""
        return jsonify({"status": "ok", "service": "auspify-ims-backend"})

    return app


if __name__ == "__main__":
    # host="0.0.0.0" listens on all network interfaces so the server is
    # reachable from containers / remote previews, not just this machine.
    # debug=True gives helpful error pages and auto-reloads on code changes.
    create_app().run(host="0.0.0.0", port=5000, debug=True)
