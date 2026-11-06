"""Serving the production build of the React app from Flask (static_site.py)."""

import gzip

import pytest

from app import create_app

INDEX_HTML = '<!doctype html><html><head><script type="module" src="/assets/app-abc123.js"></script></head><body><div id="root"></div></body></html>'
BIG_JS = "console.log('hello');\n" * 200          # > 1 KB so it is worth compressing
SMALL_TXT = "robots"                                # < 1 KB, served as-is


@pytest.fixture
def dist(tmp_path):
    """A fake Vite build: index.html plus one hashed asset."""
    folder = tmp_path / "dist"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text(INDEX_HTML)
    (folder / "assets" / "app-abc123.js").write_text(BIG_JS)
    (folder / "robots.txt").write_text(SMALL_TXT)
    # A canary just OUTSIDE dist: it must never be served.
    (tmp_path / "secret.txt").write_text("root:SECRET")
    return folder


@pytest.fixture
def site(tmp_path, dist):
    app = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.db"),
        "AUTO_SEED": False,
        "FRONTEND_DIST": str(dist),
    })
    return app.test_client()


def test_root_serves_index_html_with_csp_and_no_frame_denial(site):
    response = site.get("/")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert b'<div id="root">' in response.data
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.headers["Content-Security-Policy"].startswith("default-src 'self'; script-src 'self';")
    assert "frame-ancestors" not in response.headers["Content-Security-Policy"]
    assert "X-Frame-Options" not in response.headers          # embeddable in a preview
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("path", ["/products", "/stock", "/reports", "/manage", "/products?stock_status=low&page=2",
                                  "/some/deep/client/route"])
def test_client_side_routes_fall_back_to_index_html(site, path):
    response = site.get(path)
    assert response.status_code == 200 and response.mimetype == "text/html"
    assert b'<div id="root">' in response.data


def test_hashed_assets_are_immutable_and_gzipped_when_accepted(site):
    plain = site.get("/assets/app-abc123.js")
    assert plain.status_code == 200
    assert plain.mimetype in ("text/javascript", "application/javascript")
    assert plain.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert "Content-Encoding" not in plain.headers
    assert plain.data.decode() == BIG_JS

    zipped = site.get("/assets/app-abc123.js", headers={"Accept-Encoding": "gzip, deflate, br"})
    assert zipped.status_code == 200
    assert zipped.headers["Content-Encoding"] == "gzip"
    assert zipped.headers["Vary"] == "Accept-Encoding"
    assert len(zipped.data) < len(BIG_JS) / 5
    assert gzip.decompress(zipped.data).decode() == BIG_JS


def test_small_files_are_not_compressed(site):
    response = site.get("/robots.txt", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert "Content-Encoding" not in response.headers
    assert response.data.decode() == SMALL_TXT
    assert response.headers["Cache-Control"] == "no-cache"   # not under /assets, so not immutable


def test_missing_files_are_404_not_html(site):
    for path in ["/assets/missing.js", "/favicon.ico", "/logo.png", "/assets/app-abc123.js.map"]:
        response = site.get(path)
        assert response.status_code == 404, path
        assert response.mimetype == "application/json"


@pytest.mark.parametrize("path", ["/assets/../secret.txt", "/assets/..%2f..%2fsecret.txt", "/..%2fsecret.txt",
                                  "/%2e%2e/secret.txt", "/assets/%00.js", "/secret.txt"])
def test_path_traversal_attempts_never_leave_dist(site, path):
    response = site.get(path)
    assert response.status_code == 404, path
    assert response.mimetype == "application/json"
    assert b"root:" not in response.data


def test_api_routes_are_untouched(site):
    assert site.get("/api/health").get_json()["status"] == "ok"
    missing = site.get("/api/does-not-exist")
    assert missing.status_code == 404 and missing.mimetype == "application/json"
    assert missing.headers["X-Frame-Options"] == "DENY"
    assert missing.headers["Cache-Control"] == "no-store"
    assert site.delete("/api/reports/summary").status_code == 405
    assert site.get("/api/stock/in").status_code == 405        # POST-only endpoint: still 405, not 404
    assert site.get("/api").status_code == 404
    assert site.get("/apiary").status_code == 200              # a client route that merely starts with "api"


def test_without_a_build_the_root_explains_what_to_do(client):
    """The default test app points FRONTEND_DIST at a folder that does not exist."""
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_json()
    assert "npm run build" in body["message"]
    assert body["api_health"] == "/api/health"
    assert client.get("/products").status_code == 404     # no SPA fallback without a build
