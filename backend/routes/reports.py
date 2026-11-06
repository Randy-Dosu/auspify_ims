"""Reporting endpoints: /api/reports  (implemented in Step 3)."""

from flask import Blueprint

bp = Blueprint("reports", __name__, url_prefix="/api/reports")
