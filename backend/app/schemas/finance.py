"""Personal finance schemas. Amounts are rupees as numbers (2 decimal places)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import BillFrequency, PaymentAccount, SavingsGoalStatus, TransactionKind

Amount = Field(..., gt=0, le=10_000_000_000)


def _clean_category(v: str | None) -> str | None:
    if v is None:
        return v
    v = " ".join(v.split())
    if not v:
        raise ValueError("Category can't be blank.")
    return v[:60]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Transactions -----------------------------------------------------------------


class TransactionCreate(BaseModel):
    kind: TransactionKind = TransactionKind.EXPENSE
    amount: float = Amount
    category: str = Field(..., min_length=1, max_length=60)
    account: PaymentAccount = PaymentAccount.UPI
    occurred_on: date | None = Field(None, description="Local date; defaults to today")
    note: str | None = Field(None, max_length=255)

    _category = field_validator("category")(_clean_category)


class TransactionUpdate(BaseModel):
    kind: TransactionKind | None = None
    amount: float | None = Field(None, gt=0, le=10_000_000_000)
    category: str | None = Field(None, min_length=1, max_length=60)
    account: PaymentAccount | None = None
    occurred_on: date | None = None
    note: str | None = Field(None, max_length=255)

    _category = field_validator("category")(_clean_category)


class TransactionOut(_Out):
    id: int
    kind: TransactionKind
    amount: float
    category: str
    account: str
    occurred_on: date
    note: str | None
    bill_id: int | None
    created_at: datetime


# --- Budgets ----------------------------------------------------------------------


class BudgetSet(BaseModel):
    category: str = Field(..., min_length=1, max_length=60)
    monthly_limit: float = Amount

    _category = field_validator("category")(_clean_category)


class BudgetOut(_Out):
    id: int
    category: str
    monthly_limit: float


class BudgetStatus(BaseModel):
    id: int
    category: str
    monthly_limit: float
    spent: float
    remaining: float
    percent: int


# --- Bills ------------------------------------------------------------------------


class BillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    amount: float = Amount
    category: str = Field("Bills & Utilities", min_length=1, max_length=60)
    account: PaymentAccount = PaymentAccount.UPI
    frequency: BillFrequency = BillFrequency.MONTHLY
    next_due: date
    note: str | None = Field(None, max_length=255)

    _category = field_validator("category")(_clean_category)


class BillUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    amount: float | None = Field(None, gt=0, le=10_000_000_000)
    category: str | None = Field(None, min_length=1, max_length=60)
    account: PaymentAccount | None = None
    frequency: BillFrequency | None = None
    next_due: date | None = None
    active: bool | None = None
    note: str | None = Field(None, max_length=255)

    _category = field_validator("category")(_clean_category)


class BillOut(_Out):
    id: int
    name: str
    amount: float
    category: str
    account: str
    frequency: BillFrequency
    next_due: date
    last_paid_on: date | None
    active: bool
    note: str | None
    days_until_due: int = 0


class BillPay(BaseModel):
    paid_on: date | None = Field(None, description="Local date; defaults to today")
    amount: float | None = Field(None, gt=0, le=10_000_000_000, description="If it differed from usual")


# --- Savings goals ------------------------------------------------------------------


class SavingsGoalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    target_amount: float = Amount
    saved_amount: float = Field(0, ge=0, le=10_000_000_000)
    deadline: date | None = None
    note: str | None = Field(None, max_length=255)


class SavingsGoalUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    target_amount: float | None = Field(None, gt=0, le=10_000_000_000)
    saved_amount: float | None = Field(None, ge=0, le=10_000_000_000)
    deadline: date | None = None
    status: SavingsGoalStatus | None = None
    note: str | None = Field(None, max_length=255)


class SavingsContribution(BaseModel):
    amount: float = Field(..., description="Rupees to add (negative to withdraw)", ge=-10_000_000_000, le=10_000_000_000)


class SavingsGoalOut(_Out):
    id: int
    name: str
    target_amount: float
    saved_amount: float
    deadline: date | None
    status: SavingsGoalStatus
    note: str | None
    percent: int = 0


# --- Summary ------------------------------------------------------------------------


class CategoryTotal(BaseModel):
    category: str
    amount: float
    budget: float | None = None


class DayTotal(BaseModel):
    day: date
    expense: float
    income: float


class FinanceSummary(BaseModel):
    month: str  # YYYY-MM
    today: date
    income: float
    expense: float
    net: float
    previous_month_expense: float
    by_category: list[CategoryTotal]
    income_by_category: list[CategoryTotal]
    daily: list[DayTotal]
    budgets: list[BudgetStatus]
    bills_due: list[BillOut]
    savings: list[SavingsGoalOut]
    recent: list[TransactionOut]


class Categories(BaseModel):
    expense: list[str]
    income: list[str]
