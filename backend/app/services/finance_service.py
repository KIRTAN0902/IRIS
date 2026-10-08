"""Personal finance logic shared by the API, the agent's tools and IRIS's situation."""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.models.enums import BillFrequency, SavingsGoalStatus, TransactionKind
from app.models.finance import FinanceBill, FinanceBudget, FinanceTransaction, SavingsGoal
from app.models.user import User
from app.schemas.finance import (
    BillCreate,
    BillOut,
    BillUpdate,
    BudgetStatus,
    CategoryTotal,
    DayTotal,
    FinanceSummary,
    SavingsGoalCreate,
    SavingsGoalOut,
    SavingsGoalUpdate,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
)
from app.utils.datetime import to_local, utcnow

EXPENSE_CATEGORIES = [
    "Food & Dining",
    "Groceries",
    "Transport",
    "Shopping",
    "Bills & Utilities",
    "Rent",
    "Subscriptions",
    "EMI & Loans",
    "Health",
    "Education",
    "Entertainment",
    "Travel",
    "Personal Care",
    "Gifts & Donations",
    "Other",
]
INCOME_CATEGORIES = ["Salary", "Stipend", "Freelance", "Business", "Gifts", "Refund", "Interest", "Other"]

# How far ahead "upcoming bills" look.
BILLS_HORIZON_DAYS = 30


def today_for(user: User) -> date:
    return to_local(utcnow(), user.timezone).date()


def money(value: Decimal | float) -> float:
    return round(float(value), 2)


def inr(value: Decimal | float) -> str:
    """₹ with Indian digit grouping: ₹1,23,456.50"""
    amount = round(float(value), 2)
    sign = "-" if amount < 0 else ""
    whole, _, paise = f"{abs(amount):.2f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"{sign}₹{whole}" + ("" if paise == "00" else f".{paise}")


def month_bounds(month: str | None, today: date) -> tuple[date, date]:
    """[first day, first day of next month) for ``YYYY-MM`` (default: this month)."""
    if month:
        try:
            year, mon = (int(p) for p in month.split("-"))
            first = date(year, mon, 1)
        except ValueError as exc:
            raise ValidationAppError("Month must look like 2026-10.") from exc
    else:
        first = today.replace(day=1)
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return first, nxt


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    year, month = d.year + m // 12, m % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def advance_due(d: date, frequency: str) -> date | None:
    return {
        BillFrequency.WEEKLY.value: lambda: d + timedelta(days=7),
        BillFrequency.MONTHLY.value: lambda: add_months(d, 1),
        BillFrequency.QUARTERLY.value: lambda: add_months(d, 3),
        BillFrequency.YEARLY.value: lambda: add_months(d, 12),
    }.get(frequency, lambda: None)()


def _get(db: Session, model, user: User, obj_id: int, what: str):
    row = db.query(model).filter(model.id == obj_id, model.user_id == user.id).first()
    if row is None:
        raise NotFoundError(f"{what} not found.")
    return row


# --- Transactions ---------------------------------------------------------------------


def create_transaction(db: Session, user: User, data: TransactionCreate, *, bill_id: int | None = None) -> FinanceTransaction:
    tx = FinanceTransaction(
        user_id=user.id,
        kind=data.kind.value,
        amount=Decimal(str(data.amount)),
        category=data.category,
        account=data.account.value,
        occurred_on=data.occurred_on or today_for(user),
        note=data.note,
        bill_id=bill_id,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def update_transaction(db: Session, user: User, tx_id: int, data: TransactionUpdate) -> FinanceTransaction:
    tx = _get(db, FinanceTransaction, user, tx_id, "Transaction")
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is None and key in {"kind", "amount", "category", "account", "occurred_on"}:
            continue
        if key == "amount":
            value = Decimal(str(value))
        elif hasattr(value, "value"):
            value = value.value
        setattr(tx, key, value)
    db.commit()
    db.refresh(tx)
    return tx


def delete_transaction(db: Session, user: User, tx_id: int) -> None:
    db.delete(_get(db, FinanceTransaction, user, tx_id, "Transaction"))
    db.commit()


def list_transactions(
    db: Session,
    user: User,
    *,
    month: str | None = None,
    kind: str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 200,
) -> list[FinanceTransaction]:
    q = db.query(FinanceTransaction).filter(FinanceTransaction.user_id == user.id)
    if month:
        first, nxt = month_bounds(month, today_for(user))
        q = q.filter(FinanceTransaction.occurred_on >= first, FinanceTransaction.occurred_on < nxt)
    if kind:
        q = q.filter(FinanceTransaction.kind == kind)
    if category:
        q = q.filter(FinanceTransaction.category == category)
    if search:
        q = q.filter(FinanceTransaction.note.ilike(f"%{search}%") | FinanceTransaction.category.ilike(f"%{search}%"))
    return (
        q.order_by(FinanceTransaction.occurred_on.desc(), FinanceTransaction.id.desc()).limit(limit).all()
    )


# --- Budgets ---------------------------------------------------------------------------


def set_budget(db: Session, user: User, category: str, monthly_limit: float) -> FinanceBudget:
    budget = (
        db.query(FinanceBudget)
        .filter(FinanceBudget.user_id == user.id, FinanceBudget.category == category)
        .first()
    )
    if budget is None:
        budget = FinanceBudget(user_id=user.id, category=category)
        db.add(budget)
    budget.monthly_limit = Decimal(str(monthly_limit))
    db.commit()
    db.refresh(budget)
    return budget


def delete_budget(db: Session, user: User, budget_id: int) -> None:
    db.delete(_get(db, FinanceBudget, user, budget_id, "Budget"))
    db.commit()


def budget_statuses(db: Session, user: User, first: date, nxt: date) -> list[BudgetStatus]:
    spent = _expense_by_category(db, user, first, nxt)
    out = []
    for b in db.query(FinanceBudget).filter(FinanceBudget.user_id == user.id).order_by(FinanceBudget.category).all():
        limit, used = money(b.monthly_limit), spent.get(b.category, 0.0)
        out.append(
            BudgetStatus(
                id=b.id,
                category=b.category,
                monthly_limit=limit,
                spent=round(used, 2),
                remaining=round(limit - used, 2),
                percent=round(used / limit * 100) if limit else 0,
            )
        )
    return out


# --- Bills ------------------------------------------------------------------------------


def bill_out(bill: FinanceBill, today: date) -> BillOut:
    out = BillOut.model_validate(bill)
    out.days_until_due = (bill.next_due - today).days
    return out


def create_bill(db: Session, user: User, data: BillCreate) -> FinanceBill:
    bill = FinanceBill(
        user_id=user.id,
        **{**data.model_dump(), "amount": Decimal(str(data.amount)), "account": data.account.value, "frequency": data.frequency.value},
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return bill


def update_bill(db: Session, user: User, bill_id: int, data: BillUpdate) -> FinanceBill:
    bill = _get(db, FinanceBill, user, bill_id, "Bill")
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is None and key != "note":
            continue
        if key == "amount":
            value = Decimal(str(value))
        elif hasattr(value, "value"):
            value = value.value
        setattr(bill, key, value)
    db.commit()
    db.refresh(bill)
    return bill


def delete_bill(db: Session, user: User, bill_id: int) -> None:
    db.delete(_get(db, FinanceBill, user, bill_id, "Bill"))
    db.commit()


def list_bills(db: Session, user: User, *, include_inactive: bool = True) -> list[FinanceBill]:
    q = db.query(FinanceBill).filter(FinanceBill.user_id == user.id)
    if not include_inactive:
        q = q.filter(FinanceBill.active.is_(True))
    return q.order_by(FinanceBill.active.desc(), FinanceBill.next_due).all()


def pay_bill(
    db: Session, user: User, bill_id: int, *, paid_on: date | None = None, amount: float | None = None
) -> tuple[FinanceBill, FinanceTransaction]:
    """Record the payment as an expense and move the bill to its next due date."""
    from app.models.enums import PaymentAccount

    bill = _get(db, FinanceBill, user, bill_id, "Bill")
    if not bill.active:
        raise ValidationAppError(f"{bill.name} is no longer active.")
    tx = create_transaction(
        db,
        user,
        TransactionCreate(
            kind=TransactionKind.EXPENSE,
            amount=amount or money(bill.amount),
            category=bill.category,
            account=PaymentAccount(bill.account),
            occurred_on=paid_on or today_for(user),
            note=f"{bill.name} (bill)",
        ),
        bill_id=bill.id,
    )
    bill.last_paid_on = tx.occurred_on
    following = advance_due(bill.next_due, bill.frequency)
    if following is None:
        bill.active = False
    else:
        bill.next_due = following
    db.commit()
    db.refresh(bill)
    return bill, tx


# --- Savings goals ------------------------------------------------------------------------


def savings_out(goal: SavingsGoal) -> SavingsGoalOut:
    out = SavingsGoalOut.model_validate(goal)
    target = money(goal.target_amount)
    out.percent = min(100, round(money(goal.saved_amount) / target * 100)) if target else 0
    return out


def _settle_status(goal: SavingsGoal) -> None:
    if goal.status == SavingsGoalStatus.ARCHIVED.value:
        return
    reached = Decimal(goal.saved_amount) >= Decimal(goal.target_amount)
    goal.status = (SavingsGoalStatus.ACHIEVED if reached else SavingsGoalStatus.ACTIVE).value


def create_savings_goal(db: Session, user: User, data: SavingsGoalCreate) -> SavingsGoal:
    goal = SavingsGoal(
        user_id=user.id,
        name=data.name,
        target_amount=Decimal(str(data.target_amount)),
        saved_amount=Decimal(str(data.saved_amount)),
        deadline=data.deadline,
        note=data.note,
    )
    _settle_status(goal)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def update_savings_goal(db: Session, user: User, goal_id: int, data: SavingsGoalUpdate) -> SavingsGoal:
    goal = _get(db, SavingsGoal, user, goal_id, "Savings goal")
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is None and key not in {"deadline", "note"}:
            continue
        if key in {"target_amount", "saved_amount"}:
            value = Decimal(str(value))
        elif hasattr(value, "value"):
            value = value.value
        setattr(goal, key, value)
    if "status" not in changes:
        _settle_status(goal)
    db.commit()
    db.refresh(goal)
    return goal


def add_to_savings_goal(db: Session, user: User, goal_id: int, amount: float) -> SavingsGoal:
    goal = _get(db, SavingsGoal, user, goal_id, "Savings goal")
    goal.saved_amount = max(Decimal("0"), Decimal(goal.saved_amount) + Decimal(str(amount)))
    _settle_status(goal)
    db.commit()
    db.refresh(goal)
    return goal


def delete_savings_goal(db: Session, user: User, goal_id: int) -> None:
    db.delete(_get(db, SavingsGoal, user, goal_id, "Savings goal"))
    db.commit()


def list_savings_goals(db: Session, user: User) -> list[SavingsGoal]:
    order = {"ACTIVE": 0, "ACHIEVED": 1, "ARCHIVED": 2}
    goals = db.query(SavingsGoal).filter(SavingsGoal.user_id == user.id).all()
    return sorted(goals, key=lambda g: (order.get(g.status, 3), g.deadline or date.max, g.id))


# --- Summary --------------------------------------------------------------------------------


def _month_rows(db: Session, user: User, first: date, nxt: date) -> list[FinanceTransaction]:
    return (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.user_id == user.id,
            FinanceTransaction.occurred_on >= first,
            FinanceTransaction.occurred_on < nxt,
        )
        .all()
    )


def _expense_by_category(db: Session, user: User, first: date, nxt: date) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for t in _month_rows(db, user, first, nxt):
        if t.kind == TransactionKind.EXPENSE.value:
            totals[t.category] += float(t.amount)
    return totals


def summary(db: Session, user: User, month: str | None = None) -> FinanceSummary:
    today = today_for(user)
    first, nxt = month_bounds(month, today)
    rows = _month_rows(db, user, first, nxt)

    expense_cat: dict[str, float] = defaultdict(float)
    income_cat: dict[str, float] = defaultdict(float)
    daily: dict[date, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for t in rows:
        amount = float(t.amount)
        if t.kind == TransactionKind.EXPENSE.value:
            expense_cat[t.category] += amount
            daily[t.occurred_on][0] += amount
        else:
            income_cat[t.category] += amount
            daily[t.occurred_on][1] += amount

    budgets = budget_statuses(db, user, first, nxt)
    limits = {b.category: b.monthly_limit for b in budgets}
    prev_first, _ = month_bounds(f"{add_months(first, -1):%Y-%m}", today)
    previous = sum(_expense_by_category(db, user, prev_first, first).values())

    last_day = min(nxt - timedelta(days=1), today) if first <= today else nxt - timedelta(days=1)
    days = [first + timedelta(days=i) for i in range((last_day - first).days + 1)] if last_day >= first else []

    horizon = today + timedelta(days=BILLS_HORIZON_DAYS)
    bills = [b for b in list_bills(db, user, include_inactive=False) if b.next_due <= horizon]

    income, expense = sum(income_cat.values()), sum(expense_cat.values())
    return FinanceSummary(
        month=f"{first:%Y-%m}",
        today=today,
        income=round(income, 2),
        expense=round(expense, 2),
        net=round(income - expense, 2),
        previous_month_expense=round(previous, 2),
        by_category=[
            CategoryTotal(category=c, amount=round(a, 2), budget=limits.get(c))
            for c, a in sorted(expense_cat.items(), key=lambda kv: -kv[1])
        ],
        income_by_category=[
            CategoryTotal(category=c, amount=round(a, 2)) for c, a in sorted(income_cat.items(), key=lambda kv: -kv[1])
        ],
        daily=[DayTotal(day=d, expense=round(daily[d][0], 2), income=round(daily[d][1], 2)) for d in days],
        budgets=budgets,
        bills_due=[bill_out(b, today) for b in bills],
        savings=[savings_out(g) for g in list_savings_goals(db, user) if g.status != SavingsGoalStatus.ARCHIVED.value],
        recent=[TransactionOut.model_validate(t) for t in list_transactions(db, user, limit=6)],
    )


def situation_brief(db: Session, user: User) -> dict | None:
    """What IRIS should keep in mind about money right now (None when unused)."""
    today = today_for(user)
    first, nxt = month_bounds(None, today)
    has_any = (
        db.query(FinanceTransaction.id).filter(FinanceTransaction.user_id == user.id).first()
        or db.query(FinanceBill.id).filter(FinanceBill.user_id == user.id).first()
        or db.query(FinanceBudget.id).filter(FinanceBudget.user_id == user.id).first()
        or db.query(SavingsGoal.id).filter(SavingsGoal.user_id == user.id).first()
    )
    if not has_any:
        return None
    rows = _month_rows(db, user, first, nxt)
    spent = sum(float(t.amount) for t in rows if t.kind == TransactionKind.EXPENSE.value)
    earned = sum(float(t.amount) for t in rows if t.kind == TransactionKind.INCOME.value)
    soon = today + timedelta(days=3)
    return {
        "month": f"{first:%B}",
        "spent": round(spent, 2),
        "earned": round(earned, 2),
        "budgets_near_limit": [
            {"category": b.category, "percent": b.percent, "remaining": b.remaining}
            for b in budget_statuses(db, user, first, nxt)
            if b.percent >= 80
        ],
        "bills_due": [
            {"id": b.id, "name": b.name, "amount": money(b.amount), "due": f"{b.next_due:%a %d %b}", "days": (b.next_due - today).days}
            for b in list_bills(db, user, include_inactive=False)
            if b.next_due <= soon
        ],
    }


def render_brief(brief: dict | None) -> list[str]:
    if not brief:
        return []
    lines = [f"\nMONEY ({brief['month']}): spent {inr(brief['spent'])}, earned {inr(brief['earned'])}"]
    for b in brief["bills_due"]:
        when = "OVERDUE" if b["days"] < 0 else "today" if b["days"] == 0 else f"in {b['days']}d"
        lines.append(f"- Bill #{b['id']} {b['name']} {inr(b['amount'])} due {b['due']} ({when})")
    for b in brief["budgets_near_limit"]:
        state = "over budget" if b["remaining"] < 0 else f"{inr(b['remaining'])} left"
        lines.append(f"- Budget {b['category']}: {b['percent']}% used ({state})")
    return lines
