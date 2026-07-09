"""
API TESTS for invoice endpoints — happy paths AND the negative / edge cases
that matter most in a billing system (over-limit, invalid amounts, wrong
state transitions, missing records).
"""
from datetime import date, timedelta

# A due date 30 days out, as the API expects (ISO string).
DUE = (date.today() + timedelta(days=30)).isoformat()


def _make_buyer(client, limit=100_000, name="Acme K.K."):
    """Small helper: create a buyer and return its JSON. Keeps tests short."""
    return client.post("/buyers", json={"name": name, "credit_limit": limit}).json()


def test_create_invoice_within_limit(client):
    buyer = _make_buyer(client)
    r = client.post("/invoices", json={"buyer_id": buyer["id"], "amount": 60_000, "due_date": DUE})
    assert r.status_code == 201
    body = r.json()
    assert body["amount"] == 60_000
    assert body["status"] == "ISSUED"
    assert body["due_date"] == DUE


def test_create_invoice_over_limit_is_rejected(client):
    buyer = _make_buyer(client, limit=100_000)
    # Use 60,000, leaving 40,000 available...
    client.post("/invoices", json={"buyer_id": buyer["id"], "amount": 60_000, "due_date": DUE})
    # ...then try 50,000 which exceeds the remaining 40,000.
    r = client.post("/invoices", json={"buyer_id": buyer["id"], "amount": 50_000, "due_date": DUE})
    assert r.status_code == 422
    assert "Credit limit exceeded" in r.json()["detail"]


def test_create_invoice_at_exact_limit_is_allowed(client):
    """Boundary case: an invoice for exactly the remaining credit must succeed."""
    buyer = _make_buyer(client, limit=100_000)
    r = client.post("/invoices", json={"buyer_id": buyer["id"], "amount": 100_000, "due_date": DUE})
    assert r.status_code == 201


def test_create_invoice_invalid_amount_is_422(client):
    buyer = _make_buyer(client)
    for bad_amount in (0, -5):
        r = client.post("/invoices", json={"buyer_id": buyer["id"], "amount": bad_amount, "due_date": DUE})
        assert r.status_code == 422, f"amount={bad_amount} should be rejected"


def test_create_invoice_for_missing_buyer_is_404(client):
    r = client.post("/invoices", json={"buyer_id": 999, "amount": 1000, "due_date": DUE})
    assert r.status_code == 404


def test_credit_updates_after_invoice_then_payment(client):
    buyer = _make_buyer(client, limit=100_000)
    inv = client.post(
        "/invoices", json={"buyer_id": buyer["id"], "amount": 60_000, "due_date": DUE}
    ).json()

    # After issuing: outstanding 60k, available 40k.
    credit = client.get(f"/buyers/{buyer['id']}/credit").json()
    assert credit["outstanding"] == 60_000
    assert credit["available"] == 40_000

    # Pay it: credit frees back up.
    client.post(f"/invoices/{inv['id']}/pay")
    credit = client.get(f"/buyers/{buyer['id']}/credit").json()
    assert credit["outstanding"] == 0
    assert credit["available"] == 100_000


def test_pay_invoice_twice_is_conflict(client):
    buyer = _make_buyer(client)
    inv = client.post(
        "/invoices", json={"buyer_id": buyer["id"], "amount": 1000, "due_date": DUE}
    ).json()

    first = client.post(f"/invoices/{inv['id']}/pay")
    assert first.status_code == 200
    assert first.json()["status"] == "PAID"

    second = client.post(f"/invoices/{inv['id']}/pay")
    assert second.status_code == 409          # already paid -> conflict
    assert second.json()["detail"] == "Invoice already paid"


def test_pay_missing_invoice_is_404(client):
    assert client.post("/invoices/999/pay").status_code == 404


def test_get_missing_invoice_is_404(client):
    assert client.get("/invoices/999").status_code == 404


def test_list_invoices_filters_by_buyer_and_status(client):
    a = _make_buyer(client, name="A")
    b = _make_buyer(client, name="B")
    inv_a = client.post("/invoices", json={"buyer_id": a["id"], "amount": 1000, "due_date": DUE}).json()
    client.post("/invoices", json={"buyer_id": b["id"], "amount": 2000, "due_date": DUE})
    client.post(f"/invoices/{inv_a['id']}/pay")   # buyer A's invoice becomes PAID

    # Filter by buyer A -> only A's one invoice.
    only_a = client.get(f"/invoices?buyer_id={a['id']}").json()
    assert len(only_a) == 1
    assert only_a[0]["buyer_id"] == a["id"]

    # Filter by status PAID -> only the paid one (A's).
    paid = client.get("/invoices?status=PAID").json()
    assert len(paid) == 1
    assert paid[0]["id"] == inv_a["id"]

    # No filter -> both invoices.
    assert len(client.get("/invoices").json()) == 2
