"""
Business logic — pure functions only. No database, no web framework here.

Why a separate file?
    Each function below takes plain inputs and returns a plain output.
    It doesn't touch a database or the network, so it is *deterministic*:
    same inputs -> same output, every time. That makes it trivial to
    unit-test (see tests/unit/). This is the bottom, widest layer of the
    "test pyramid": many tiny, fast tests.

Money rule:
    All amounts are WHOLE JAPANESE YEN as `int`. We never use float for
    money (0.1 + 0.2 != 0.3 in floating point — unacceptable for a billing
    system). JPY has no minor unit, so plain integers are exact and safe.
"""
from __future__ import annotations

from datetime import date


# --------------------------------------------------------------------------
# Credit rules (Kessai-style credit screening)
# --------------------------------------------------------------------------
def available_credit(credit_limit: int, outstanding: int) -> int:
    """How much credit the buyer can still use right now.

    available = credit_limit - (sum of unpaid invoices)
    Can go negative in theory; callers treat <=0 as "no room left".
    """
    return credit_limit - outstanding


def can_issue_invoice(credit_limit: int, outstanding: int, amount: int) -> bool:
    """Return True if a new invoice of `amount` is allowed for this buyer.

    Rules:
      * amount must be positive,
      * amount must fit inside the buyer's remaining credit.

    This mirrors what Kessai does before guaranteeing a payment: check that
    the buyer is still within their approved credit line.
    """
    if amount <= 0:
        return False
    return amount <= available_credit(credit_limit, outstanding)


# --------------------------------------------------------------------------
# Overdue rules
# --------------------------------------------------------------------------
def is_overdue(due_date: date, paid: bool, today: date) -> bool:
    """An invoice is overdue only if it is unpaid AND past its due date."""
    return (not paid) and (today > due_date)


def days_overdue(due_date: date, today: date) -> int:
    """How many days past the due date we are (0 if not past due yet)."""
    delta_days = (today - due_date).days
    return max(delta_days, 0)


def late_fee(amount: int, days_late: int, daily_rate_bps: int = 10) -> int:
    """Late fee, computed with INTEGER math so there is no float in money.

    `daily_rate_bps` is the daily rate in *basis points* (1 bp = 0.01%).
    Default 10 bp = 0.10% of the invoice amount per day late.

    Example: 100,000 yen, 5 days late, 10 bp
             -> 100000 * 10 * 5 // 10000 = 500 yen.

    Using `//` (integer division) floors to whole yen — deterministic and
    exact, which is exactly what a financial system needs.
    """
    if days_late <= 0:
        return 0
    return amount * daily_rate_bps * days_late // 10000
