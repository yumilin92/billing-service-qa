# QA Strategy

How this project is tested, and why it's tested this way. The goal is to catch
defects at the cheapest, fastest layer possible, and to prove correct behaviour
automatically on every change.

## The test pyramid

```
        ▲  fewer, slower, most realistic
        │      E2E  (Playwright)        2 tests  — real browser + real server
        │      API  (pytest+TestClient) ~17     — every endpoint over HTTP
        │      Unit (pytest)            ~20      — pure business rules
        ▼  many, fast, cheapest
```

- **Unit tests** (`tests/unit/`) target the pure functions in `app/domain.py`
  (credit screening, overdue, late fees). They have no database or network, so
  they run in microseconds and pin down every boundary. This is where most of
  the logic risk lives, so this is where most of the tests are.
- **API/integration tests** (`tests/api/`) drive every endpoint over real HTTP
  using FastAPI's `TestClient`, each against a fresh in-memory database. They
  verify status codes, JSON bodies, validation, and the wiring between layers.
- **End-to-end tests** (`tests/e2e/`) use Playwright to click the actual UI in a
  real browser against a running server. Slow and realistic — kept to the two
  most important journeys only.

## What we deliberately test beyond the happy path

Risk-based testing means spending effort where a defect would hurt most. In a
billing system that means **money and state**:

| Risk | Test |
|---|---|
| Buyer borrows beyond their credit limit | over-limit invoice → `422`; exactly-at-limit → allowed; one yen over → rejected |
| Invalid money reaches the ledger | zero / negative amount → `422` (schema validation) |
| Double-charging / bad state change | paying an already-paid invoice → `409` |
| Operating on data that isn't there | missing buyer / invoice → `404` |
| Floating-point money errors | amounts are integer yen; late-fee uses integer (basis-point) math |
| Stale derived numbers | outstanding balance is computed live, never stored |

## Test isolation

Every unit/API test gets its own brand-new in-memory database (see
`tests/conftest.py`), injected by overriding FastAPI's `get_db` dependency.
Tests never share state, never touch `billing.db`, and can run in any order.
E2E tests run against a throwaway SQLite file in a background server process.

## Continuous Integration

`.github/workflows/ci.yml` runs on every push and pull request:

1. **Lint** with `ruff`.
2. **Install** the Playwright browser.
3. **Run the full suite** with coverage, failing the build if coverage drops
   below **90%** (currently ~96%).

A red build blocks the change — quality is enforced, not hoped for.

## Load / reliability smoke

`tests/load/locustfile.py` is a Locust smoke test: it spins up concurrent
virtual users hitting `/health`, invoice creation, and credit lookups. It's a
guard against gross performance or reliability regressions, not a benchmark.
Baseline on a laptop: 20 users, **0% errors**, single-digit-millisecond responses.

## What I'd add next (roadmap for a real product)

- Contract tests / schema snapshots for the public API.
- Property-based tests (Hypothesis) for the money math.
- Migrations (Alembic) + tests that migrations apply cleanly.
- Test data factories for larger scenarios.
- Mutation testing to measure how good the tests actually are.
