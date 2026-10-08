"""Personal finance: transactions, monthly budgets, bills and savings goals.

Money is stored as ``Numeric(12, 2)`` rupees. Dates that matter to the user
(when money moved, when a bill is due) are plain local calendar dates, so they
never shift with timezones.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import BillFrequency, PaymentAccount, SavingsGoalStatus

Money = Numeric(12, 2)


class _Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now()
    )


class FinanceTransaction(_Timestamps, Base):
    __tablename__ = "finance_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    category: Mapped[str] = mapped_column(String(60), index=True)
    account: Mapped[str] = mapped_column(String(20), default=PaymentAccount.UPI.value)
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str | None] = mapped_column(String(255), default=None)
    # Set when the transaction is a bill payment.
    bill_id: Mapped[int | None] = mapped_column(
        ForeignKey("finance_bills.id", ondelete="SET NULL"), default=None, index=True
    )


class FinanceBudget(_Timestamps, Base):
    """A monthly spending limit for one expense category."""

    __tablename__ = "finance_budgets"
    __table_args__ = (UniqueConstraint("user_id", "category", name="uq_finance_budget_category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(60))
    monthly_limit: Mapped[Decimal] = mapped_column(Money)


class FinanceBill(_Timestamps, Base):
    """A recurring payment: rent, EMI, subscription, recharge..."""

    __tablename__ = "finance_bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Money)
    category: Mapped[str] = mapped_column(String(60))
    account: Mapped[str] = mapped_column(String(20), default=PaymentAccount.UPI.value)
    frequency: Mapped[str] = mapped_column(String(12), default=BillFrequency.MONTHLY.value)
    next_due: Mapped[date] = mapped_column(Date, index=True)
    last_paid_on: Mapped[date | None] = mapped_column(Date, default=None)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    note: Mapped[str | None] = mapped_column(String(255), default=None)


class SavingsGoal(_Timestamps, Base):
    __tablename__ = "savings_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    target_amount: Mapped[Decimal] = mapped_column(Money)
    saved_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), server_default="0")
    deadline: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[str] = mapped_column(String(12), default=SavingsGoalStatus.ACTIVE.value)
    note: Mapped[str | None] = mapped_column(String(255), default=None)
