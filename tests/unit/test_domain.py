"""
UNIT TESTS — the bottom of the test pyramid.

These test the pure functions in app/domain.py directly. No database, no HTTP,
so they run in microseconds. We use @pytest.mark.parametrize to run the SAME
test body against MANY input/expected pairs — one test, many cases, including
the tricky boundaries (exactly at the limit, one yen over, etc.).
"""
from datetime import date

import pytest

from app import domain


# --------------------------------------------------------------------------
# available_credit
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "credit_limit, outstanding, expected",
    [
        (100_000, 0, 100_000),        # nothing used yet
        (100_000, 60_000, 40_000),    # partly used
        (100_000, 100_000, 0),        # fully used
        (100_000, 120_000, -20_000),  # over-extended (can go negative)
    ],
)
def test_available_credit(credit_limit, outstanding, expected):
    assert domain.available_credit(credit_limit, outstanding) == expected


# --------------------------------------------------------------------------
# can_issue_invoice — the credit-screening rule, incl. boundaries
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "credit_limit, outstanding, amount, allowed",
    [
        (100_000, 0, 40_000, True),      # comfortably within
        (100_000, 60_000, 40_000, True),  # EXACTLY at the limit -> allowed
        (100_000, 60_000, 40_001, False), # ONE yen over -> rejected
        (100_000, 100_000, 1, False),     # no room left
        (100_000, 0, 0, False),           # zero amount -> not allowed
        (100_000, 0, -5, False),          # negative amount -> not allowed
    ],
)
def test_can_issue_invoice(credit_limit, outstanding, amount, allowed):
    assert domain.can_issue_invoice(credit_limit, outstanding, amount) is allowed


# --------------------------------------------------------------------------
# is_overdue
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "due_date, paid, today, expected",
    [
        (date(2026, 1, 10), False, date(2026, 1, 11), True),   # unpaid + past due
        (date(2026, 1, 10), True,  date(2026, 1, 11), False),  # paid -> never overdue
        (date(2026, 1, 10), False, date(2026, 1, 10), False),  # exactly on due date
        (date(2026, 1, 10), False, date(2026, 1, 5), False),   # before due date
    ],
)
def test_is_overdue(due_date, paid, today, expected):
    assert domain.is_overdue(due_date, paid, today) is expected


# --------------------------------------------------------------------------
# days_overdue
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "due_date, today, expected",
    [
        (date(2026, 1, 10), date(2026, 1, 15), 5),  # 5 days late
        (date(2026, 1, 10), date(2026, 1, 10), 0),  # due today -> 0
        (date(2026, 1, 10), date(2026, 1, 1), 0),   # not due yet -> 0, never negative
    ],
)
def test_days_overdue(due_date, today, expected):
    assert domain.days_overdue(due_date, today) == expected


# --------------------------------------------------------------------------
# late_fee — integer money math
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "amount, days_late, rate_bps, expected",
    [
        (100_000, 5, 10, 500),    # 100000 * 10bp * 5 / 10000 = 500
        (100_000, 0, 10, 0),      # not late -> no fee
        (100_000, -3, 10, 0),     # negative days -> no fee
        (100_000, 1, 10, 100),    # one day: 100000 * 10bp / 10000 = 100
        (100_000, 5, 25, 1_250),  # a higher rate (25 bp/day)
    ],
)
def test_late_fee(amount, days_late, rate_bps, expected):
    assert domain.late_fee(amount, days_late, rate_bps) == expected
