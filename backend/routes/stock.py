"""Stock movement endpoints: /api/stock  (implemented in Step 2)."""

from flask import Blueprint

bp = Blueprint("stock", __name__, url_prefix="/api/stock")
