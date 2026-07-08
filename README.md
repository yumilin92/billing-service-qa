# billing-service-qa

A small **B2B deferred-payment (invoice) service** plus the **automated test suite and CI** around it — built as a focused demonstration of **QA / SDET** engineering.

The domain mirrors a B2B "buy now, pay later" / invoice-guarantee product (a buyer has a credit limit; invoices are credit-screened, then paid or go overdue). The point of the project is not the service itself — it's **how it is tested**.

---

## Why this project

Good quality engineering is about designing for testability and then proving behaviour automatically. This repo shows:

- **A layered, testable design** — pure business rules are separated from the web and database layers, so each can be tested at the right level.
- **A real test pyramid** — many fast unit tests, focused API/integration tests, and end-to-end tests.
- **Negative & edge-case testing** — not just the happy path: over-limit invoices, invalid input, double payments, missing records.
- **Continuous Integration** — every push runs lint + the full suite with a coverage report.
- **A reliability check** — a small load-test smoke to catch gross performance regressions.

## Domain model

| Entity | Fields | Rules |
|---|---|---|
| **Buyer** | name, `credit_limit` (yen) | — |
| **Invoice** | buyer, `amount` (yen), issue/due dates, status | must pass **credit screening** on creation; `ISSUED → PAID`; overdue if unpaid past due date |

Money is always **whole Japanese yen as `int`** — never floating point.

## Architecture

```
app/
  domain.py     # pure business logic (credit, overdue, late fees) — no I/O
  models.py     # SQLAlchemy tables + Pydantic request/response schemas
  database.py   # DB engine + per-request session (overridable in tests)
  main.py       # FastAPI app: thin HTTP routes
tests/
  unit/         # fast tests of domain.py           (Phase 2)
  api/          # HTTP tests of the endpoints        (Phase 2)
  e2e/          # Playwright end-to-end              (Phase 3)
  load/         # Locust smoke load test             (Phase 5)
```

## Tech

Python · FastAPI · SQLAlchemy 2.0 · SQLite · pytest · Playwright · GitHub Actions · Locust

## Running locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload          # http://127.0.0.1:8000/docs
```

Interactive API docs are auto-generated at `/docs`.

## Roadmap

- [x] **Phase 1** — Billing service (buyers, credit-screened invoices, payments, credit summary)
- [ ] **Phase 2** — Test pyramid: unit tests (domain) + API tests (happy / negative / edge)
- [ ] **Phase 3** — End-to-end tests with Playwright
- [ ] **Phase 4** — CI on GitHub Actions (lint + tests + coverage badge)
- [ ] **Phase 5** — Load-test smoke (Locust) + written QA strategy notes
