"""
End-to-end tests: a real browser drives the demo UI.

`page` comes from the pytest-playwright plugin (a fresh browser tab per test).
`live_server` (from conftest.py) is the running app's base URL.

We cover two journeys:
  1. the happy path — create a buyer, then an invoice within the limit;
  2. the key business error — an invoice over the credit limit shows the
     server's error message to the user.
"""
import pytest

# Mark these so they can be selected/skipped separately (they need a browser).
pytestmark = pytest.mark.e2e


def test_create_buyer_then_invoice_happy_path(live_server, page):
    page.goto(live_server + "/")

    # Step 1: create a buyer (the form is pre-filled with Acme K.K. / 100000).
    page.click("#buyer-submit")
    page.wait_for_selector("#buyer-result.ok")
    assert "created" in page.text_content("#buyer-result")

    # The UI auto-filled the buyer id into the invoice form. Create an invoice
    # for 60,000 (within the 100,000 limit).
    page.fill("#invoice-amount", "60000")
    page.click("#invoice-submit")

    page.wait_for_selector("#invoice-result.ok")
    result = page.text_content("#invoice-result")
    assert "ISSUED" in result
    assert "60000" in result


def test_invoice_over_limit_shows_error(live_server, page):
    page.goto(live_server + "/")

    # Buyer with a small limit of 10,000.
    page.fill("#buyer-limit", "10000")
    page.click("#buyer-submit")
    page.wait_for_selector("#buyer-result.ok")

    # Try to invoice 50,000 — well over the limit.
    page.fill("#invoice-amount", "50000")
    page.click("#invoice-submit")

    page.wait_for_selector("#invoice-result.error")
    assert "Credit limit exceeded" in page.text_content("#invoice-result")
