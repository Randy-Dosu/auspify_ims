# Testing & Quality Guide

This document collects every way the project is verified:

1. [Automated backend tests (pytest)](#1-automated-backend-tests-pytest)
2. [Automated frontend tests (Vitest)](#2-automated-frontend-tests-vitest)
3. [Live smoke suite](#3-live-smoke-suite)
4. [Data-integrity audit](#4-data-integrity-audit)
5. [Security checks](#5-security-checks)
6. [Manual end-to-end checklist](#6-manual-end-to-end-checklist)
7. [Edge cases and how they are handled](#7-edge-cases-and-how-they-are-handled)

---

## 1. Automated backend tests (pytest)

Every test gets a **fresh temporary SQLite database** (no seed data), so tests
are independent and can run in any order.

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt      # first time only
python -m pytest                         # quiet
python -m pytest -v                      # one line per test
python -m pytest tests/test_stock.py     # one file
```

| File | Tests | What it proves |
|------|------:|----------------|
| `tests/test_crud.py` | 45 | Product/category/supplier CRUD, validation messages per field, duplicate SKU (case-insensitive) → 409, price rounding (half-up), quantity cap, update cannot touch quantity, delete cascades history, in-use lookups → 409, DB-level FK and CHECK enforcement |
| `tests/test_stock.py` | 27 | Stock in/out/adjust, ledger == quantity after mixed ops, over-withdrawal/zero-stock/negative-adjust → 400 with a clear message and **no side effects**, invalid payloads, simulated crash between UPDATE and INSERT rolls back (atomicity), DB CHECK as last line of defence, **25 concurrent withdrawals → exactly 10 succeed**, 30 interleaved operations keep the ledger consistent |
| `tests/test_reports.py` | 14 | Summary equals a hand calculation, low-stock ordering and shortfall, valuation per category, movements date filter + zero-filled days, invalid ranges → 400, top-moving limit, empty database returns zeros, CSV structure and formula-injection escaping |
| `tests/test_filters.py` | 52 | Each filter alone, **every pair of filters equals the intersection** of the single results, all filters together, sorting both ways (name case-insensitive, joined columns), pagination counts/overlap/beyond-end, 21 invalid-parameter cases → 400 naming the field, LIKE wildcards treated literally, SQL-injection payloads are plain text |
| `tests/test_security.py` | 44 | Security headers on every response, JSON (not HTML) 404/405, malformed bodies, 1 MB body limit → 413, mass-assignment ignored, SKU whitelist, non-finite/odd price encodings rejected, bad ids → 404 not 500, CORS allow-list, product_id type checks |

| `tests/test_static_site.py` | 18 | Flask serving the production build: `index.html` for client routes, hashed assets immutable + gzipped, small files uncompressed, missing files → 404 JSON (never HTML), path-traversal attempts stay inside `dist/`, API routing untouched (GET on a POST-only endpoint is still 405), helpful JSON on `/` when there is no build |

**Latest run:** `200 passed in 6.1s`.

### Mutation check (does the suite catch real bugs?)

Two deliberate bugs were introduced and the suite was re-run:

| Mutation | Result |
|----------|--------|
| `database.transaction()` commits instead of rolling back on error | `test_failure_after_quantity_update_rolls_everything_back` **FAILED** (caught) |
| `stock_out` no longer checks `quantity_in_stock >= ?` in its UPDATE | `test_over_withdrawal_is_rejected_with_clear_message_and_no_side_effects` **FAILED** (caught); stock still never went negative thanks to the DB CHECK constraint |

## 2. Automated frontend tests (Vitest + Testing Library)

```bash
cd frontend
npx vitest run        # 36 tests in 5 files
npm run lint          # oxlint
npm run build         # production build must succeed
```

Covers: product table rendering/sorting/empty state, lookup manager CRUD and
error display, Products page URL-driven filters/sorting/pagination with a
debounced search, Stock Movements picker + history + deep links, Reports page
cards/charts/CSV button. `fetch` is mocked (`src/test/mockApi.js`) so the
tests never need a running backend.

## 3. Live smoke suite

`scripts/smoke_test.py` drives a **running** backend through HTTP and checks
213 behaviours across Steps 0-4 (health, CRUD, constraints, stock operations,
reports vs. manual calculation, filters, pagination, injection payloads). It
cleans up everything it creates.

```bash
python3 scripts/smoke_test.py                              # directly against :5000
python3 scripts/smoke_test.py --base http://localhost:5173 # through the Vite proxy
python3 scripts/smoke_test.py --only 3                     # a single step
```

**Latest run:** `213 passed, 0 failed` (direct and via proxy).

## 4. Data-integrity audit

`backend/audit.py` opens the database **read-only** and checks the invariants
the application promises to keep. It needs no running server.

```bash
cd backend && source .venv/bin/activate
python audit.py                   # instance/inventory.db
python audit.py path/to/file.db   # any other database
echo $?                           # 0 = all good, 1 = discrepancy, 2 = cannot open
```

Checks:

1. `quantity_in_stock == Σ IN − Σ OUT + Σ ADJUSTMENT` for every product
2. Reported inventory value `== Σ quantity × unit_price` (computed independently in Python)
3. No orphaned `category_id` / `supplier_id` / `product_id`
4. No negative quantities, prices or reorder levels; every transaction type is valid
5. SKUs and category names are unique (case-insensitive)
6. SQLite `PRAGMA integrity_check` and `PRAGMA foreign_key_check`

**Latest run against the live database** (after the full smoke suite):

```
Auditing /home/user/auspify_ims/backend/instance/inventory.db
  6 categories, 4 suppliers, 22 products, 161 stock_transactions
PASS  Stock ledger matches quantity_in_stock (22 products checked)
PASS  Inventory value equals sum(quantity x unit_price) (total 96,129.00)
PASS  No orphaned foreign keys
PASS  No negative stock, prices or invalid transactions
PASS  SKUs and category names are unique
PASS  SQLite integrity_check / foreign_key_check

ALL CHECKS PASSED (6/6)
```

The audit was also run against a **deliberately corrupted copy** (ledger drift,
negative price and stock, orphan category and transaction, bogus transaction
type written with constraints disabled). It reported `4 CHECK(S) FAILED` and
listed every injected fault, exit code 1.

## 5. Security checks

| Area | Protection | Verified by |
|------|-----------|-------------|
| SQL injection | Parameterised queries everywhere; sort column/order from a whitelist; LIKE wildcards escaped | `test_filters.py`, smoke Step 4 |
| CSV formula injection | Cells starting with `= + - @ \t \r` are prefixed with `'` | `test_reports.py` |
| Input validation | Every field type/range checked; errors name the field; unknown fields ignored | `test_crud.py`, `test_security.py` |
| Integer overflow | Ids limited to 1..2^63−1 (custom URL converter), quantities ≤ 1e9, prices ≤ 1e9 | `test_security.py`, `test_crud.py` |
| Oversized bodies | `MAX_CONTENT_LENGTH` = 1 MB → 413 JSON | `test_security.py` |
| Information leaks | Unhandled errors → `{"error": "Internal server error."}`, never a stack trace | `test_stock.py` |
| Browser hardening | Every response: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`. API responses: `X-Frame-Options: DENY`, `Cache-Control: no-store`. HTML pages: `Content-Security-Policy` (`default-src 'self'`, no inline scripts, optional `frame-ancestors` via `IMS_FRAME_ANCESTORS`) | `test_security.py`, `test_static_site.py` |
| Static file serving | Only files inside `frontend/dist`; traversal (`..`, encoded) → 404; asset-like URLs never answered with HTML | `test_static_site.py` |
| CORS | Only `http://localhost:5173` / `127.0.0.1:5173` (configurable) | `test_security.py` |
| Race conditions | `BEGIN IMMEDIATE` transactions + conditional UPDATE + DB CHECK | `test_stock.py` concurrency tests |
| XSS | API returns JSON only; React escapes text when rendering | `test_security.py`, smoke `<script>` check |
| Dependencies | `pip-audit -r requirements.txt` and `npm audit` | both report **0 known vulnerabilities** |

## 6. Manual end-to-end checklist

Run the app (single server: `npm run build` then `python app.py` → <http://localhost:5000>,
or dev mode: `python app.py` + `npm run dev` → <http://localhost:5173>) and work
through the table. Tick Pass/Fail as you go.

> A headless-Chromium pass over the built app (every page, a deep-linked
> filter URL, a typed search) reported no console errors, failed requests or
> CSP violations - but it cannot judge looks, so the visual items below still
> need a human.

### Dashboard

| # | Action | Expected | Pass/Fail |
|---|--------|----------|-----------|
| D1 | Open `/` | Summary cards show product count, units, total value, low-stock and out-of-stock counts; backend status "ok" | ☐ |
| D2 | Compare "Total value" with Reports → Valuation total | Identical figure | ☐ |
| D3 | Click "Restock" on a low-stock row | Stock Movements opens with that product pre-selected | ☐ |

### Products

| # | Action | Expected | Pass/Fail |
|---|--------|----------|-----------|
| P1 | Click "Add product", submit empty form | Inline errors for SKU, name and price; nothing saved | ☐ |
| P2 | Create `TEST-100`, price `12.345`, qty `5`, reorder `10` | Row appears with price `12.35` and a **Low** badge | ☐ |
| P3 | Create another product with SKU `test-100` | Error "Already exists." (case-insensitive) | ☐ |
| P4 | Enter price `-1` or quantity `-5` | Rejected with a clear message | ☐ |
| P5 | Edit `TEST-100`, change name and price | Table updates; quantity field is not editable | ☐ |
| P6 | Type `test` in search | After ~300 ms only matching rows remain; results count updates; URL contains `?search=test` | ☐ |
| P7 | Pick a category, a supplier, stock status "Low", price 1-100 | Rows satisfy **all** filters; results count matches | ☐ |
| P8 | Click "Clear filters" | All filters reset; full list returns | ☐ |
| P9 | Click the "Price" header twice | Sorted ascending, then descending; arrow and `aria-sort` change | ☐ |
| P10 | Set page size 10, go to page 2 | "Showing 11-20 of N"; different rows; URL has `page=2` | ☐ |
| P11 | Search for `zzzz` | "No products match these filters. Try clearing some of them." | ☐ |
| P12 | Reload the browser with filters in the URL | Same filters applied after reload | ☐ |
| P13 | Delete `TEST-100` and confirm | Row disappears; its history is gone | ☐ |

### Manage (categories & suppliers)

| # | Action | Expected | Pass/Fail |
|---|--------|----------|-----------|
| M1 | Add category "Office" twice | Second attempt shows "Already exists." | ☐ |
| M2 | Rename a category | New name shows in the Products category column | ☐ |
| M3 | Delete a category that has products | Error "... used by N product(s)" and it stays | ☐ |
| M4 | Add a supplier with e-mail `not-an-email` | Validation error | ☐ |

### Stock Movements

| # | Action | Expected | Pass/Fail |
|---|--------|----------|-----------|
| S1 | Type part of a SKU in "Filter products" | Picker narrows; hint shows "Showing X of Y products" | ☐ |
| S2 | Select a product, Stock In 10 with reason "Purchase" | Quantity rises by 10; new IN row at the top of history | ☐ |
| S3 | Stock Out more than available | Error "Insufficient stock for SKU: requested X, only N available."; quantity unchanged; no history row | ☐ |
| S4 | Stock Out exactly the available amount | Quantity 0; badge "Out of stock" | ☐ |
| S5 | Adjust to counted quantity 7 | ADJUSTMENT row with signed difference; quantity is 7 | ☐ |
| S6 | Adjust with delta that would go below zero | Rejected; nothing changes | ☐ |
| S7 | Check history total | IN − OUT ± ADJ equals the displayed quantity | ☐ |

### Reports

| # | Action | Expected | Pass/Fail |
|---|--------|----------|-----------|
| R1 | Open `/reports` | Cards, bar + pie charts by category, movements line chart, low-stock table | ☐ |
| R2 | Change the date range to a period with no movements | Line chart shows zeros, no error | ☐ |
| R3 | Enter `from` after `to` | Error message; charts unchanged | ☐ |
| R4 | Export low-stock CSV | File downloads, opens in a spreadsheet with a header row and one row per low-stock product | ☐ |
| R5 | Name a product `=1+1`, export CSV, open it | Cell shows the text `'=1+1`, not `2` | ☐ |
| R6 | Perform a Stock Out, return to Reports | Movements and low-stock update | ☐ |

### Cross-cutting / security

| # | Action | Expected | Pass/Fail |
|---|--------|----------|-----------|
| X1 | Visit `http://localhost:5000/api/products?sort=evil` | 400 JSON naming `sort` | ☐ |
| X2 | Visit `http://localhost:5000/api/products/99999999999999999999` | 404 JSON, not 500 | ☐ |
| X3 | Create a product named `<img src=x onerror=alert(1)>` and view it in the UI | Shown as plain text, no alert | ☐ |
| X4 | Stop the backend, use the UI | Friendly error messages, no blank screens | ☐ |
| X5 | Run `python backend/audit.py` after all of the above | `ALL CHECKS PASSED (6/6)` | ☐ |

## 7. Edge cases and how they are handled

| Edge case | Behaviour | Where it is enforced | Tested in |
|-----------|-----------|----------------------|-----------|
| **Empty database** | All lists return `items: []`; every report returns zeros (never `null`); movements still produce a zero-filled day series; CSV has a header row only | `COALESCE(..., 0)` in report SQL, Python zero-fill | `test_reports.py::test_empty_database_reports_zeros_not_errors`, `test_filters.py::test_empty_database_list_is_well_formed` |
| **Duplicate SKU** | `409 {"details": {"sku": "Already exists."}}`; comparison is case-insensitive (`ABC-1` vs `abc-1`) | `UNIQUE COLLATE NOCASE` + IntegrityError → 409 | `test_crud.py::test_duplicate_sku_is_rejected_case_insensitively`, `test_update_to_existing_sku_conflicts` |
| **Over-withdrawal** | `400 "Insufficient stock for SKU: requested X, only N available."`; quantity and history untouched | Conditional `UPDATE ... WHERE quantity_in_stock >= ?` inside a transaction; `CHECK (quantity_in_stock >= 0)` as backstop | `test_stock.py` (3 tests) |
| **Simultaneous updates** | Writers are serialised by `BEGIN IMMEDIATE`; 25 threads taking 1 unit from 10 → exactly 10×201 and 15×400, final quantity 0, ledger consistent | `database.transaction()` | `test_stock.py::test_concurrent_*` |
| **Zero stock** | Allowed (status `out`); further OUT is rejected; IN restores it; stock status badge and low-stock report include it with `shortfall = reorder_level` | `stock_status()` helper, report SQL | `test_stock.py`, `test_reports.py` |
| **Decimal prices** | Parsed with `Decimal`, rounded half-up to 2 dp (`12.345` → `12.35`, `19.999` → `20.00`); strings must be plain decimals (`"1e3"`, `"1,000"`, `"$5"` rejected); `-0` stored as `0`; `NaN`/`Infinity` rejected | `validation.parse_price` | `test_crud.py::test_prices_are_rounded_half_up_to_two_decimals`, `test_security.py` price tests |
| **Large quantities** | Up to 1 000 000 000 per field/movement; larger values → 400 "Must be at most 1000000000."; ids > 2^63−1 → 404; `page` ≤ 1 000 000, `per_page` ≤ 100 | `MAX_QUANTITY`, `IdConverter`, `_parse_list_params` | `test_crud.py::test_large_quantities_are_supported_up_to_the_cap`, `test_stock.py` parametrised quantities, `test_security.py::test_bad_ids_in_urls_are_404_not_500` |
| **Crash mid-operation** | UPDATE and INSERT share one transaction; a failure after the UPDATE rolls both back and returns a generic 500 | `database.transaction()` | `test_stock.py::test_failure_after_quantity_update_rolls_everything_back` |
| **Lookups in use** | Deleting a category/supplier that products reference → 409 "... used by N product(s)" | `ON DELETE RESTRICT` + explicit count | `test_crud.py` |
| **Hostile text** | HTML stored verbatim, returned as JSON with `nosniff`; React escapes on render; CSV cells escaped against formulas | API design, `_csv_safe` | `test_security.py`, `test_reports.py` |
| **Pagination beyond the end** | `200` with `items: []` and the correct `total` / `total_pages` | `list_products` | `test_filters.py::test_pagination_counts_and_pages` |
