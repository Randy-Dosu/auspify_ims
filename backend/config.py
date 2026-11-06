"""
Central configuration for the Flask backend.

Values can be overridden with environment variables so the same code runs
in development, in tests and (later) in production without edits.
"""

import os

# Absolute path of the backend/ folder, used to build default file paths.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _env_list(name, default):
    """Read a comma-separated environment variable into a list of strings."""
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class Config:
    # SQLite file. Created automatically on first run (see database.init_db).
    DATABASE = os.environ.get(
        "IMS_DATABASE", os.path.join(BASE_DIR, "instance", "inventory.db")
    )

    # Insert sample data when the database is empty. Set IMS_AUTO_SEED=0 to
    # start with a blank database.
    AUTO_SEED = os.environ.get("IMS_AUTO_SEED", "1") == "1"

    # Browser origins allowed to call the API directly (CORS). The Vite dev
    # server proxies /api so it does not need CORS, but we keep the list
    # explicit instead of using "*" so unknown sites cannot call the API
    # from a user's browser.
    CORS_ORIGINS = _env_list(
        "IMS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )

    # Reject request bodies larger than 1 MB (protects against huge payloads).
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024
