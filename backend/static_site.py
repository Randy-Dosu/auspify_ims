"""
Serve the production build of the React app from Flask (optional).

    cd frontend && npm run build        # writes frontend/dist (3 small files)
    cd backend  && python app.py        # http://localhost:5000 now serves the UI too

Why this exists
---------------
The Vite dev server (npm run dev, port 5173) is perfect on a laptop, but it
ships ~10 MB of un-minified, uncompressed JavaScript per page load. Through a
slow link or a remote preview proxy that looks like "the page never loads".
The production build is ~700 KB (~200 KB gzipped) and needs no websocket, so
serving it from the same Flask process is both the faster preview and the
simplest deployment: one server, one port.

If frontend/dist does not exist this module only registers a friendly message
on "/" and the API behaves exactly as before.

What it does
------------
* /assets/<hashed file>  -> served with a one-year immutable cache (Vite puts a
                            content hash in every asset filename, so a changed
                            file always gets a new URL) and gzip when the
                            browser accepts it.
* /, /products, /stock…  -> index.html (the React router decides what to show).
* /api/…                 -> never handled here; falls through to the JSON 404.
* anything with a file extension that does not exist -> 404, so a missing
  image is never silently answered with HTML.

Security notes
--------------
* send_from_directory() refuses paths that escape the dist folder ("..").
* The HTML gets a Content-Security-Policy that only allows scripts, styles and
  API calls from this origin. No frame-ancestors rule is set so the app can be
  embedded in a sandbox preview; in production add
  "frame-ancestors 'none'" to CSP (see FRAME_ANCESTORS in config.py).
"""

import gzip
import mimetypes
import os

from flask import Response, abort, current_app, jsonify, request, send_from_directory
from werkzeug.routing import PathConverter

ASSET_CACHE = "public, max-age=31536000, immutable"
HTML_CACHE = "no-cache"
COMPRESSIBLE = {".js", ".css", ".svg", ".json", ".map", ".html", ".txt"}
MIN_GZIP_BYTES = 1024

# Compressed assets are kept in memory: (absolute path, mtime) -> gzipped bytes.
# The build has only a handful of files so this is tiny and never stale
# (a rebuild changes the mtime, and usually the filename hash as well).
_gzip_cache = {}


class NonApiPathConverter(PathConverter):
    """
    URL converter for the catch-all route that matches any path EXCEPT ones
    under /api. Doing this in the routing layer (rather than inside the view)
    keeps Flask's own behaviour for API URLs intact - e.g. GET on a POST-only
    endpoint still answers 405, and unknown API URLs still answer 404.
    """
    regex = r"(?!api(?:/|$))[^/].*?"


def _gzipped(path):
    """Return the gzip-compressed bytes of a file, compressing once per build."""
    key = (path, os.path.getmtime(path))
    if key not in _gzip_cache:
        with open(path, "rb") as fh:
            _gzip_cache[key] = gzip.compress(fh.read(), compresslevel=6)
    return _gzip_cache[key]


def _accepts_gzip():
    return "gzip" in request.headers.get("Accept-Encoding", "").lower()


def _serve_asset(dist, relative_path):
    """Serve one static file from dist/, gzipped when it is worth it."""
    absolute = os.path.join(dist, relative_path)
    _, ext = os.path.splitext(relative_path)
    is_immutable = relative_path.startswith("assets/")
    cache = ASSET_CACHE if is_immutable else HTML_CACHE

    if ext in COMPRESSIBLE and _accepts_gzip() and os.path.getsize(absolute) >= MIN_GZIP_BYTES:
        mimetype = mimetypes.guess_type(relative_path)[0] or "application/octet-stream"
        response = Response(_gzipped(absolute), mimetype=mimetype)
        response.headers["Content-Encoding"] = "gzip"
    else:
        response = send_from_directory(dist, relative_path, conditional=True)
    response.headers["Cache-Control"] = cache
    response.headers["Vary"] = "Accept-Encoding"
    return response


def register_static_site(app):
    """Attach the catch-all routes. Call once from create_app()."""
    dist = os.path.abspath(app.config["FRONTEND_DIST"])
    index_path = os.path.join(dist, "index.html")

    if not os.path.isfile(index_path):
        @app.get("/")
        def frontend_missing():
            return jsonify({
                "message": "API is running. No frontend build found - run `npm run build` in "
                           "frontend/ to serve the UI from this server, or use the Vite dev "
                           "server (npm run dev) on http://localhost:5173.",
                "api_health": "/api/health",
            })
        app.logger.info("Frontend build not found at %s; serving API only.", dist)
        return

    app.url_map.converters["nonapi"] = NonApiPathConverter

    @app.get("/", defaults={"path": ""})
    @app.get("/<nonapi:path>")
    def spa(path):
        # 1. A real file inside dist (index.html, assets/*.js, favicon…)?
        candidate = os.path.normpath(os.path.join(dist, path)) if path else index_path
        inside_dist = candidate == dist or candidate.startswith(dist + os.sep)
        if path and inside_dist and os.path.isfile(candidate):
            return _serve_asset(dist, os.path.relpath(candidate, dist))

        # 2. Looks like a file (has an extension) but does not exist -> 404,
        #    never HTML. Otherwise it is a client-side route -> index.html.
        last_segment = path.rsplit("/", 1)[-1]
        if "." in last_segment:
            abort(404)
        response = send_from_directory(dist, "index.html", conditional=True)
        response.headers["Cache-Control"] = HTML_CACHE
        return response

    app.logger.info("Serving frontend build from %s", dist)


def content_security_policy():
    """CSP for HTML pages served by the app (see module docstring)."""
    policy = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "   # React/Recharts set inline style attributes
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    frame_ancestors = current_app.config.get("FRAME_ANCESTORS")
    if frame_ancestors:
        policy += f"; frame-ancestors {frame_ancestors}"
    return policy
