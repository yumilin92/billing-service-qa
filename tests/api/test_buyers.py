"""
API TESTS for buyer endpoints — the middle of the pyramid.

Each test uses the `client` fixture (from tests/conftest.py), which talks to a
fresh in-memory database. We assert on the HTTP status code AND the JSON body.
"""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Billing Service" in r.text


def test_create_buyer(client):
    r = client.post("/buyers", json={"name": "Acme K.K.", "credit_limit": 100_000})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] > 0                 # the DB assigned an id
    assert body["name"] == "Acme K.K."
    assert body["credit_limit"] == 100_000


def test_create_buyer_rejects_bad_input(client):
    # Empty name violates min_length=1 -> 422 from Pydantic validation.
    r1 = client.post("/buyers", json={"name": "", "credit_limit": 1000})
    assert r1.status_code == 422
    # Negative credit limit violates ge=0 -> 422.
    r2 = client.post("/buyers", json={"name": "X", "credit_limit": -1})
    assert r2.status_code == 422


def test_get_buyer_roundtrip(client):
    created = client.post("/buyers", json={"name": "Beta Ltd", "credit_limit": 50_000}).json()
    r = client.get(f"/buyers/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_get_missing_buyer_returns_404(client):
    r = client.get("/buyers/999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Buyer not found"


def test_credit_summary_missing_buyer_returns_404(client):
    r = client.get("/buyers/999/credit")
    assert r.status_code == 404


def test_credit_summary_for_new_buyer(client):
    buyer = client.post("/buyers", json={"name": "Gamma", "credit_limit": 80_000}).json()
    r = client.get(f"/buyers/{buyer['id']}/credit")
    assert r.status_code == 200
    assert r.json() == {
        "buyer_id": buyer["id"],
        "credit_limit": 80_000,
        "outstanding": 0,        # no invoices yet
        "available": 80_000,
    }
