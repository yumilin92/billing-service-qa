"""
Two different kinds of "model" live here — keep them straight:

1. ORM models (SQLAlchemy): Buyer, Invoice
   -> describe how rows are stored in database TABLES.

2. Schemas (Pydantic): *Create / *Out
   -> describe the shape of JSON coming IN and going OUT of the API,
      and validate it automatically.

Why separate them? The public API contract (schemas) can stay stable even
if we later change how things are stored (tables). Mixing them is a common
source of bugs and leaks (e.g. accidentally returning internal fields).
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class InvoiceStatus(str, Enum):
    """The lifecycle states an invoice can be in.

    Inheriting from `str` means the value serialises to plain text
    ("ISSUED"/"PAID") in JSON, which is easy to read and assert on in tests.
    """
    ISSUED = "ISSUED"
    PAID = "PAID"


# ==========================================================================
# ORM models  (how data is stored)
# ==========================================================================
class Buyer(Base):
    __tablename__ = "buyers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    credit_limit: Mapped[int]  # whole yen

    invoices: Mapped[list["Invoice"]] = relationship(back_populates="buyer")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("buyers.id"))
    amount: Mapped[int]  # whole yen
    issue_date: Mapped[date]
    due_date: Mapped[date]
    status: Mapped[InvoiceStatus] = mapped_column(default=InvoiceStatus.ISSUED)
    paid_at: Mapped[datetime | None] = mapped_column(default=None)

    buyer: Mapped["Buyer"] = relationship(back_populates="invoices")


# ==========================================================================
# Pydantic schemas  (the API contract, with validation)
# ==========================================================================
class BuyerCreate(BaseModel):
    """Body for POST /buyers. Field(...) rules reject bad input with 422
    automatically, before our code even runs."""
    name: str = Field(min_length=1, max_length=120)
    credit_limit: int = Field(ge=0, description="Whole yen, 0 or more")


class BuyerOut(BaseModel):
    # from_attributes=True lets Pydantic read straight from an ORM object.
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    credit_limit: int


class BuyerCredit(BaseModel):
    """Response for GET /buyers/{id}/credit — a live credit summary."""
    buyer_id: int
    credit_limit: int
    outstanding: int
    available: int


class InvoiceCreate(BaseModel):
    """Body for POST /invoices. `gt=0` means the amount MUST be positive —
    a negative or zero invoice is rejected with 422 automatically."""
    buyer_id: int
    amount: int = Field(gt=0, description="Whole yen, must be positive")
    due_date: date


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    buyer_id: int
    amount: int
    issue_date: date
    due_date: date
    status: InvoiceStatus
