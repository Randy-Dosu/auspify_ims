"""
Application error types and the handlers that turn them into JSON responses.

Raising one of these anywhere in a request (route or model code) produces a
consistent JSON error body:

    {"error": "human readable message", "details": {"field": "why"}}

so the frontend can always rely on the same shape.
"""

import sqlite3

from flask import jsonify
from werkzeug.exceptions import HTTPException


class APIError(Exception):
    """Base class: an error with an HTTP status code and a safe message."""

    status_code = 400

    def __init__(self, message, details=None, status_code=None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code


class ValidationError(APIError):
    """The client sent invalid input (400)."""

    status_code = 400


class NotFoundError(APIError):
    """The requested record does not exist (404)."""

    status_code = 404


class ConflictError(APIError):
    """The request conflicts with existing data, e.g. duplicate SKU (409)."""

    status_code = 409


def _json_error(message, status, details=None):
    body = {"error": message}
    if details:
        body["details"] = details
    return jsonify(body), status


def register_error_handlers(app):
    """Attach JSON error handlers to the app (called from create_app)."""

    @app.errorhandler(APIError)
    def handle_api_error(err):
        return _json_error(err.message, err.status_code, err.details)

    @app.errorhandler(sqlite3.IntegrityError)
    def handle_integrity_error(err):
        """
        Safety net for database constraints the validation layer did not
        catch. We map SQLite's technical message to a friendly one and never
        echo raw SQL details to the client.
        """
        text = str(err)
        if "UNIQUE constraint failed" in text:
            return _json_error("A record with the same unique value already exists.", 409)
        if "FOREIGN KEY constraint failed" in text:
            return _json_error("Referenced record does not exist or is still in use.", 400)
        if "CHECK constraint failed" in text:
            return _json_error("A value violates a database rule (e.g. negative stock or price).", 400)
        return _json_error("Database constraint violated.", 400)

    @app.errorhandler(HTTPException)
    def handle_http_exception(err):
        """404 for unknown URLs, 405 wrong method, 413 body too large, ..."""
        return _json_error(err.description or err.name, err.code)

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        """
        Anything else is a bug. Log the full traceback on the server but return
        a generic message - stack traces must never reach the client.
        """
        app.logger.exception("Unhandled error: %s", err)
        return _json_error("Internal server error.", 500)
