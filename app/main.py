"""
The web layer: the FastAPI application and its HTTP endpoints.

Notice the routes are THIN. Each one:
  1. validates input (Pydantic did most of it already),
  2. calls the pure business rules in domain.py,
  3. reads/writes through the database session,
  4. returns a schema object.
Thin routes are easy to read and easy to integration-test (Phase 2).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import domain, models
from .database import Base, engine, get_db

# Create the tables if they don't exist yet. Fine for a demo; a production
# app would use migrations (e.g. Alembic) instead of create_all.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Billing Service — Kessai-style deferred payment",
    version="0.1.0",
    description="A small B2B deferred-payment API: buyers with credit limits, "
                "credit-screened invoices, payments and overdue logic.",
)


def _outstanding(db: Session, buyer_id: int) -> int:
    """Sum of a buyer's UNPAID invoice amounts.

    We compute it live from the invoices instead of storing a running total.
    Computing avoids "the stored number drifted out of sync" bugs — a classic
    source of financial defects.
    """
    unpaid = db.scalars(
        select(models.Invoice).where(
            models.Invoice.buyer_id == buyer_id,
            models.Invoice.status == models.InvoiceStatus.ISSUED,
        )
    ).all()
    return sum(inv.amount for inv in unpaid)


@app.get("/health")
def health():
    """Liveness probe — handy for CI and uptime checks."""
    return {"status": "ok"}


# --------------------------------------------------------------------------
# Buyers
# --------------------------------------------------------------------------
@app.post("/buyers", response_model=models.BuyerOut, status_code=201)
def create_buyer(payload: models.BuyerCreate, db: Session = Depends(get_db)):
    buyer = models.Buyer(name=payload.name, credit_limit=payload.credit_limit)
    db.add(buyer)
    db.commit()
    db.refresh(buyer)  # reload so buyer.id (assigned by the DB) is populated
    return buyer


@app.get("/buyers/{buyer_id}", response_model=models.BuyerOut)
def get_buyer(buyer_id: int, db: Session = Depends(get_db)):
    buyer = db.get(models.Buyer, buyer_id)
    if buyer is None:
        raise HTTPException(status_code=404, detail="Buyer not found")
    return buyer


@app.get("/buyers/{buyer_id}/credit", response_model=models.BuyerCredit)
def get_credit(buyer_id: int, db: Session = Depends(get_db)):
    buyer = db.get(models.Buyer, buyer_id)
    if buyer is None:
        raise HTTPException(status_code=404, detail="Buyer not found")
    outstanding = _outstanding(db, buyer_id)
    return models.BuyerCredit(
        buyer_id=buyer_id,
        credit_limit=buyer.credit_limit,
        outstanding=outstanding,
        available=domain.available_credit(buyer.credit_limit, outstanding),
    )


# --------------------------------------------------------------------------
# Invoices
# --------------------------------------------------------------------------
@app.post("/invoices", response_model=models.InvoiceOut, status_code=201)
def create_invoice(payload: models.InvoiceCreate, db: Session = Depends(get_db)):
    buyer = db.get(models.Buyer, payload.buyer_id)
    if buyer is None:
        raise HTTPException(status_code=404, detail="Buyer not found")

    outstanding = _outstanding(db, payload.buyer_id)

    # The Kessai-style credit screening — the heart of the domain:
    if not domain.can_issue_invoice(buyer.credit_limit, outstanding, payload.amount):
        available = domain.available_credit(buyer.credit_limit, outstanding)
        raise HTTPException(
            status_code=422,
            detail=f"Credit limit exceeded: amount {payload.amount} "
                   f"exceeds available credit {available}",
        )

    invoice = models.Invoice(
        buyer_id=payload.buyer_id,
        amount=payload.amount,
        issue_date=date.today(),
        due_date=payload.due_date,
        status=models.InvoiceStatus.ISSUED,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


@app.get("/invoices/{invoice_id}", response_model=models.InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(models.Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@app.post("/invoices/{invoice_id}/pay", response_model=models.InvoiceOut)
def pay_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(models.Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    # Paying an already-paid invoice is a conflict, not a success:
    if invoice.status == models.InvoiceStatus.PAID:
        raise HTTPException(status_code=409, detail="Invoice already paid")
    invoice.status = models.InvoiceStatus.PAID
    invoice.paid_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invoice)
    return invoice


@app.get("/invoices", response_model=list[models.InvoiceOut])
def list_invoices(
    buyer_id: int | None = None,
    status: models.InvoiceStatus | None = None,
    db: Session = Depends(get_db),
):
    """List invoices, optionally filtered by buyer and/or status."""
    query = select(models.Invoice)
    if buyer_id is not None:
        query = query.where(models.Invoice.buyer_id == buyer_id)
    if status is not None:
        query = query.where(models.Invoice.status == status)
    return db.scalars(query).all()
