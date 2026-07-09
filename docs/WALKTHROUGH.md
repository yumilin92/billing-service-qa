# Build this project from scratch — a step-by-step walkthrough

This is a teaching guide. It rebuilds the whole project from an empty folder,
explaining **what** we do, **why**, and **which tool** does the job at each step.
Follow it top to bottom and you'll end up with the same repo.

Mental model of the whole thing:

> We build a small **billing API** (the "system under test"), then wrap it in
> **automated tests** at three levels, a **CI robot** that runs them on every
> change, and a **load test**. The tests are the real deliverable.

---

## Phase 0 — Setup (tools & skeleton)

### 0.1 The tools, and what each is for
- **Python 3.12** — the language.
- **venv** — a *virtual environment*: a private copy of Python + packages that
  belongs only to this project, so its dependencies never clash with other
  projects. Golden rule: one venv per project.
- **pip** — installs Python packages.
- **git** — version control (history of every change).
- **FastAPI** — the web framework (turns Python functions into HTTP endpoints).
- **uvicorn** — the web *server* that actually runs a FastAPI app.
- **SQLAlchemy** — talks to the database in Python instead of raw SQL.
- **SQLite** — a whole database in a single file; zero setup.

### 0.2 Create the folders
```bash
mkdir -p billing-service-qa/app billing-service-qa/tests
cd billing-service-qa
```
`app/` = the service; `tests/` = the tests. Keeping them apart is convention.

### 0.3 Create and activate a virtual environment
```bash
python3 -m venv .venv        # create it (a hidden .venv folder)
source .venv/bin/activate    # "enter" it — your prompt shows (.venv)
```
**Why:** now `pip install` puts packages inside `.venv`, not system-wide.
Everything below assumes the venv is active.

### 0.4 Install the runtime dependencies
```bash
pip install "fastapi" "uvicorn[standard]" "sqlalchemy"
```
We record these in **`requirements.txt`** so anyone (and the CI robot) can
recreate the exact setup:
```
fastapi>=0.110
uvicorn[standard]>=0.27
sqlalchemy>=2.0
```
`pip install -r requirements.txt` re-installs them later.

### 0.5 Start git and tell it what to ignore
```bash
git init
```
Create **`.gitignore`** so generated / machine-specific stuff never gets
committed (the venv is huge, the DB is generated, caches are noise):
```
.venv/
__pycache__/
*.pyc
*.db
.pytest_cache/
.coverage
htmlcov/
node_modules/
.DS_Store
```

---

## Phase 1 — The billing service

We build it in **layers**, because layers are what make it testable. Build the
files in this order: pure logic → data → web.

### 1.1 `app/domain.py` — pure business rules
Plain functions, no database, no web. Given inputs, return an output — nothing
else. This is where the real logic lives (credit check, overdue, late fee).

**Why first / why separate:** pure functions are *deterministic* — same input,
same output — so they're trivial to unit-test in microseconds. Example:
```python
def can_issue_invoice(credit_limit, outstanding, amount):
    if amount <= 0:
        return False
    return amount <= credit_limit - outstanding
```
**Money lesson:** all amounts are whole yen (`int`). Never `float` for money —
`0.1 + 0.2 != 0.3` in floating point, unacceptable for billing. The late fee
uses integer *basis-point* math so it stays exact.

### 1.2 `app/database.py` — the database connection
Sets up the SQLAlchemy `engine` (the connection), a `SessionLocal` factory (one
"session" = one conversation with the DB), and a `Base` class that tables
inherit from.

The important piece is the **`get_db` dependency**:
```python
def get_db():
    db = SessionLocal()
    try:
        yield db          # hand a session to the request
    finally:
        db.close()        # always close it afterwards
```
**Why `yield` not `return`:** it lets FastAPI run setup before the request and
cleanup after. And because it's a *dependency*, tests can **replace** it with a
test database later — the key to test isolation.

We also read the DB location from an environment variable so dev, tests, and CI
can each point somewhere different without editing code:
```python
SQLALCHEMY_DATABASE_URL = os.getenv("BILLING_DB_URL", "sqlite:///./billing.db")
```

### 1.3 `app/models.py` — two kinds of "model"
- **ORM models** (SQLAlchemy): `Buyer`, `Invoice` — how rows are stored in
  **tables**.
- **Schemas** (Pydantic): `BuyerCreate`, `InvoiceOut`, … — the shape of **JSON**
  in/out of the API, with automatic validation.

**Why separate:** the public API contract can stay stable even if storage
changes, and Pydantic rejects bad input *before your code runs*:
```python
class InvoiceCreate(BaseModel):
    buyer_id: int
    amount: int = Field(gt=0)   # <=0 is auto-rejected with HTTP 422
    due_date: date
```

### 1.4 `app/main.py` — the web layer (endpoints)
The FastAPI app. Each route is **thin**: validate (Pydantic already did most),
call `domain.py`, read/write via the DB session, return a schema.

Example — the credit-screening rule at the HTTP boundary:
```python
if not domain.can_issue_invoice(buyer.credit_limit, outstanding, payload.amount):
    raise HTTPException(status_code=422, detail="Credit limit exceeded ...")
```
**HTTP status codes are the API's language** — get them right, QA checks them:
`201` created · `404` not found · `409` conflict (e.g. paying twice) ·
`422` validation / business-rule violation.

### 1.5 Run it and click around
```bash
uvicorn app.main:app --reload
```
- `app.main:app` = "in file app/main.py, use the variable `app`".
- `--reload` = auto-restart when you save a file (dev convenience).
Open **http://127.0.0.1:8000/docs** — FastAPI auto-generates interactive docs
where you can send real requests. This is your first manual smoke test.

---

## Phase 2 — The test pyramid (pytest)

**pytest** is the test runner. It finds files named `test_*.py` and functions
named `test_*`, runs them, and reports pass/fail. **pytest-cov** measures how
much code the tests exercised.

```bash
pip install pytest pytest-cov
```

### 2.1 `pytest.ini` — configuration
```ini
[pytest]
pythonpath = .          # so `import app` works from the tests
testpaths = tests       # where the tests live
addopts = -q            # quiet output
```

### 2.2 `tests/conftest.py` — shared fixtures (the heart of isolation)
`conftest.py` is special: pytest loads it automatically and its **fixtures**
(reusable setup pieces) are available to every test with no import.

Two fixtures:
- **`db_session`** — a brand-new *in-memory* SQLite DB for each test
  (`sqlite://` + `StaticPool`). Built fresh, thrown away after. No test ever
  sees another test's data.
- **`client`** — a FastAPI `TestClient` whose requests use that test DB, by
  **overriding `get_db`**:
  ```python
  app.dependency_overrides[get_db] = lambda: iter([db_session])
  ```
  This is the professional way to swap real infrastructure for test
  infrastructure.

**Why isolation matters:** a test must pass or fail because of the *code*, not
because of leftover data. Isolated tests can run in any order, in parallel,
repeatably.

### 2.3 `tests/unit/test_domain.py` — unit tests
Test the pure functions directly. Use **parametrize** to run one test body over
many cases, especially **boundaries**:
```python
@pytest.mark.parametrize("limit, outstanding, amount, allowed", [
    (100_000, 60_000, 40_000, True),   # exactly at the limit -> allowed
    (100_000, 60_000, 40_001, False),  # one yen over        -> rejected
])
def test_can_issue_invoice(limit, outstanding, amount, allowed):
    assert domain.can_issue_invoice(limit, outstanding, amount) is allowed
```
Boundaries (exactly-at, one-over, zero, negative) are where bugs hide.

### 2.4 `tests/api/` — API / integration tests
Drive every endpoint over HTTP with the `client` fixture. Assert on **status
code AND body**. Cover the happy path *and*, crucially, the **negatives**:
over-limit → 422, invalid amount → 422, missing record → 404, double payment →
409. Writing negative tests ("try to break it") is the core QA skill.

### 2.5 Run with coverage
```bash
pytest --cov=app --cov-report=term-missing
```
The `Missing` column lists exact lines no test touched — a to-do list for more
tests. (We reached ~97%.)

> Real moment from building this: a test *failed* on the late-fee math — and the
> bug was in the **test's expected value**, not the code. Tests are code too;
> they can be wrong. That's normal QA work.

---

## Phase 3 — End-to-end tests (Playwright)

E2E = a real **browser** clicks a real **UI** talking to a real **server**. Most
realistic, slowest — so keep only a few, for critical journeys.

```bash
pip install pytest-playwright
python -m playwright install chromium    # downloads the browser engine
```

### 3.1 A tiny UI to drive: `app/static/index.html`
A plain HTML page with two forms (create buyer, create invoice) and vanilla
JavaScript that `fetch()`es our API. We serve it from `app/main.py`:
```python
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
```

### 3.2 `tests/e2e/conftest.py` — a `live_server` fixture
Unlike API tests (in-process), E2E needs a *real running server*. This fixture:
1. makes a throwaway temp database,
2. starts `uvicorn` in a **background process** on a free port,
3. polls `/health` until it answers,
4. hands the URL to the tests,
5. shuts it down and deletes the temp DB afterwards.

### 3.3 `tests/e2e/test_e2e_ui.py` — the browser test
`pytest-playwright` gives a `page` fixture (a browser tab). You script a human:
```python
page.goto(live_server + "/")
page.click("#buyer-submit")
page.fill("#invoice-amount", "60000")
page.click("#invoice-submit")
page.wait_for_selector("#invoice-result.ok")
assert "ISSUED" in page.text_content("#invoice-result")
```
We test two journeys: the happy path, and the over-limit error showing up in the
UI. `@pytest.mark.e2e` tags them so they can be selected/skipped separately.

---

## Phase 4 — CI on GitHub Actions

**CI (Continuous Integration)** = a robot that runs your checks automatically on
every push, so nothing broken gets in unnoticed. GitHub Actions is configured
with a YAML file in `.github/workflows/`.

### 4.1 `.github/workflows/ci.yml`
```yaml
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest        # a fresh Linux machine, provided by GitHub
    steps:
      - uses: actions/checkout@v4          # get the code
      - uses: actions/setup-python@v5      # install Python 3.12
        with: { python-version: "3.12", cache: pip }
      - run: pip install -r requirements-dev.txt
      - run: ruff check .                  # lint
      - run: python -m playwright install --with-deps chromium
      - run: pytest --cov=app --cov-fail-under=90   # tests + coverage GATE
```
**`--cov-fail-under=90`** is a *quality gate*: if coverage drops below 90%, the
build goes red and the change is blocked. Quality is enforced, not hoped for.

### 4.2 The badge
Add to `README.md`:
```
![CI](https://github.com/<user>/billing-service-qa/actions/workflows/ci.yml/badge.svg)
```
It shows green "passing" once the workflow runs — instant credibility.

### 4.3 `ruff` — the linter
```bash
pip install ruff
ruff check .
```
A linter flags dead code, unused imports, style problems — fast feedback before
tests even run.

---

## Phase 5 — Load smoke (Locust) + QA strategy

### 5.1 `tests/load/locustfile.py`
**Locust** simulates many concurrent users. This is a *smoke* test — "does it
stay healthy under load?", not a full benchmark.
```python
class BillingUser(HttpUser):
    wait_time = between(0.1, 0.5)
    def on_start(self):                       # once per simulated user
        self.buyer_id = self.client.post("/buyers", json={...}).json()["id"]
    @task(3)
    def health(self): self.client.get("/health")
    @task(2)
    def create_invoice(self): self.client.post("/invoices", json={...})
```
Run it (server must be up):
```bash
locust -f tests/load/locustfile.py --host http://127.0.0.1:8000 \
       --headless -u 20 -r 5 -t 15s
```
`-u 20` users, `-r 5` ramp/sec, `-t 15s` duration. Watch that **failures = 0**.

### 5.2 `docs/QA-STRATEGY.md`
A written explanation of the testing approach: the pyramid, *risk-based* choices
(test hardest where a bug hurts most — money and state), isolation, CI, and what
you'd add next. This shows QA **thinking**, not just code — recruiters read it.

---

## Publishing

```bash
git add -A
git commit -m "..."
gh repo create billing-service-qa --public --source=. --push
```
`gh` is GitHub's command-line tool. `--source=.` publishes this folder;
`--push` uploads it. The moment it lands, the CI workflow runs on GitHub.

---

## The one-paragraph interview summary

> "I built a small B2B billing API (FastAPI + SQLAlchemy) and wrapped it in a
> full test pyramid: parametrized unit tests for the money rules, HTTP
> integration tests covering happy paths and negatives (over-limit 422, double
> pay 409, 404s), each on an isolated in-memory database via dependency
> overrides, and Playwright end-to-end tests through a real browser. GitHub
> Actions runs ruff + the whole suite with a 90% coverage gate on every push,
> and a Locust smoke checks it holds up under concurrent load. ~97% coverage,
> green CI."
