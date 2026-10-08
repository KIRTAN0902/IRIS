"""Finance tools: IRIS can log money, manage budgets, bills and savings by chat or voice.

They call the same finance service and schemas as the Finance page.
"""

from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, Field

from app.agent.tools.actions import _with_id, make_tool
from app.agent.tools.base import Tool
from app.models.enums import TransactionKind
from app.schemas.finance import (
    BillCreate,
    BillUpdate,
    BudgetSet,
    SavingsGoalCreate,
    SavingsGoalUpdate,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
)
from app.services import finance_service as fs
from app.services.finance_service import inr


class _MonthParams(BaseModel):
    month: str | None = Field(None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM; default this month")


class _ListTransactionsParams(_MonthParams):
    kind: TransactionKind | None = None
    category: str | None = None
    search: str | None = Field(None, description="Text to find in notes/categories")
    limit: int = Field(30, ge=1, le=200)


class _IdsParams(BaseModel):
    transaction_ids: list[int] = Field(..., min_length=1, max_length=100)


class _BudgetDelete(BaseModel):
    category: str


class _BillId(BaseModel):
    bill_id: int


class _PayBill(_BillId):
    paid_on: Date | None = Field(None, description="Default today")
    amount: float | None = Field(None, gt=0, description="Only if it differed from the usual amount")


class _GoalId(BaseModel):
    goal_id: int


class _AddSavings(_GoalId):
    amount: float = Field(..., description="Rupees to add; negative to withdraw")


def _tx_line(tx) -> str:
    sign = "+" if tx.kind == TransactionKind.INCOME.value else ""
    return f"{sign}{inr(tx.amount)} {tx.category} ({tx.account}, {tx.occurred_on:%d %b})"


def _log(db, user, **p):
    tx = fs.create_transaction(db, user, TransactionCreate(**p))
    kind = "income" if tx.kind == TransactionKind.INCOME.value else "expense"
    return TransactionOut.model_validate(tx), f"Logged {kind} #{tx.id}: {_tx_line(tx)}"


def _get_finances(db, user, month=None):
    s = fs.summary(db, user, month)
    return s, f"{s.month}: spent {inr(s.expense)}, earned {inr(s.income)}"


def _get_transactions(db, user, month=None, kind=None, category=None, search=None, limit=30):
    rows = fs.list_transactions(
        db, user, month=month, kind=kind.value if kind else None, category=category, search=search, limit=limit
    )
    return [TransactionOut.model_validate(t) for t in rows], f"{len(rows)} transactions"


def _update_tx(db, user, transaction_id, **p):
    tx = fs.update_transaction(db, user, transaction_id, TransactionUpdate(**p))
    return TransactionOut.model_validate(tx), f"Updated transaction #{tx.id}: {_tx_line(tx)}"


def _delete_txs(db, user, transaction_ids):
    done, missing = [], []
    for tx_id in transaction_ids:
        try:
            fs.delete_transaction(db, user, tx_id)
            done.append(tx_id)
        except Exception:  # noqa: BLE001 -- report per item
            db.rollback()
            missing.append(tx_id)
    note = f"; not found: {missing}" if missing else ""
    return {"deleted": done, "not_found": missing}, f"Deleted {len(done)} transaction(s){note}"


def _set_budget(db, user, category, monthly_limit):
    b = fs.set_budget(db, user, category, monthly_limit)
    return {"id": b.id, "category": b.category, "monthly_limit": fs.money(b.monthly_limit)}, (
        f"Budget for {b.category}: {inr(b.monthly_limit)}/month"
    )


def _delete_budget(db, user, category):
    budget = next((b for b in fs.budget_statuses(db, user, *fs.month_bounds(None, fs.today_for(user))) if b.category.lower() == category.lower()), None)
    if budget is None:
        return {"deleted": False}, f"No budget for {category}"
    fs.delete_budget(db, user, budget.id)
    return {"deleted": True}, f"Removed the {budget.category} budget"


def _bills(db, user):
    today = fs.today_for(user)
    bills = [fs.bill_out(b, today) for b in fs.list_bills(db, user)]
    return bills, f"{len(bills)} bills"


def _create_bill(db, user, **p):
    bill = fs.create_bill(db, user, BillCreate(**p))
    return fs.bill_out(bill, fs.today_for(user)), (
        f"Added bill #{bill.id}: {bill.name} {inr(bill.amount)} {bill.frequency.lower()}, next due {bill.next_due:%d %b}"
    )


def _update_bill(db, user, bill_id, **p):
    bill = fs.update_bill(db, user, bill_id, BillUpdate(**p))
    return fs.bill_out(bill, fs.today_for(user)), f"Updated bill #{bill.id}: {bill.name}"


def _pay_bill(db, user, bill_id, paid_on=None, amount=None):
    bill, tx = fs.pay_bill(db, user, bill_id, paid_on=paid_on, amount=amount)
    nxt = f", next due {bill.next_due:%d %b}" if bill.active else ""
    return fs.bill_out(bill, fs.today_for(user)), f"Paid {bill.name} ({inr(tx.amount)}){nxt}"


def _delete_bill(db, user, bill_id):
    fs.delete_bill(db, user, bill_id)
    return {"deleted": bill_id}, f"Deleted bill #{bill_id}"


def _savings(db, user):
    goals = [fs.savings_out(g) for g in fs.list_savings_goals(db, user)]
    return goals, f"{len(goals)} savings goals"


def _create_goal(db, user, **p):
    g = fs.create_savings_goal(db, user, SavingsGoalCreate(**p))
    return fs.savings_out(g), f"Savings goal #{g.id}: {g.name}, target {inr(g.target_amount)}"


def _update_goal(db, user, goal_id, **p):
    g = fs.update_savings_goal(db, user, goal_id, SavingsGoalUpdate(**p))
    return fs.savings_out(g), f"Updated savings goal #{g.id}: {g.name}"


def _add_savings(db, user, goal_id, amount):
    g = fs.add_to_savings_goal(db, user, goal_id, amount)
    out = fs.savings_out(g)
    return out, f"{g.name}: {inr(g.saved_amount)} of {inr(g.target_amount)} ({out.percent}%)"


def _delete_goal(db, user, goal_id):
    fs.delete_savings_goal(db, user, goal_id)
    return {"deleted": goal_id}, f"Deleted savings goal #{goal_id}"


def finance_tools() -> list[Tool]:
    return [
        make_tool(
            name="log_transaction",
            description=(
                "Record money spent or received (rupees). kind EXPENSE or INCOME; pick the closest "
                f"category (expense: {', '.join(fs.EXPENSE_CATEGORIES)}; income: {', '.join(fs.INCOME_CATEGORIES)}); "
                "account UPI/CASH/CARD/BANK/WALLET/OTHER (default UPI); occurred_on is the local date (default today)."
            ),
            params=TransactionCreate,
            run=_log,
            read_only=False,
        ),
        make_tool(
            name="get_finances",
            description="Monthly money overview: income, spending by category, budgets used, bills due, savings goals, recent transactions.",
            params=_MonthParams,
            run=_get_finances,
            read_only=True,
        ),
        make_tool(
            name="get_transactions",
            description="List transactions, filtered by month, kind, category or text.",
            params=_ListTransactionsParams,
            run=_get_transactions,
            read_only=True,
        ),
        make_tool(
            name="update_transaction",
            description="Change a logged transaction (amount, category, account, date, note, kind).",
            params=_with_id(TransactionUpdate, "transaction_id", "transaction"),
            run=_update_tx,
            read_only=False,
        ),
        make_tool(
            name="delete_transactions",
            description="Delete one or more transactions by id in a single call.",
            params=_IdsParams,
            run=_delete_txs,
            read_only=False,
            destructive=True,
        ),
        make_tool(
            name="set_budget",
            description="Create or change a monthly spending limit for an expense category.",
            params=BudgetSet,
            run=_set_budget,
            read_only=False,
        ),
        make_tool(
            name="delete_budget",
            description="Remove the monthly budget for a category.",
            params=_BudgetDelete,
            run=_delete_budget,
            read_only=False,
            destructive=True,
        ),
        make_tool(
            name="get_bills",
            description="List recurring bills/subscriptions with next due dates.",
            run=_bills,
            read_only=True,
        ),
        make_tool(
            name="create_bill",
            description="Add a recurring payment (rent, EMI, subscription, recharge). frequency WEEKLY/MONTHLY/QUARTERLY/YEARLY/ONCE; next_due is a local date.",
            params=BillCreate,
            run=_create_bill,
            read_only=False,
        ),
        make_tool(
            name="update_bill",
            description="Change a bill (amount, due date, frequency, pause with active=false...).",
            params=_with_id(BillUpdate, "bill_id", "bill"),
            run=_update_bill,
            read_only=False,
        ),
        make_tool(
            name="pay_bill",
            description="Mark a bill paid: logs the expense and moves it to the next due date.",
            params=_PayBill,
            run=_pay_bill,
            read_only=False,
        ),
        make_tool(
            name="delete_bill",
            description="Delete a bill.",
            params=_BillId,
            run=_delete_bill,
            read_only=False,
            destructive=True,
        ),
        make_tool(
            name="get_savings_goals",
            description="List savings goals with progress.",
            run=_savings,
            read_only=True,
        ),
        make_tool(
            name="create_savings_goal",
            description="Start a savings goal, e.g. 'Laptop', target 80000, optional deadline.",
            params=SavingsGoalCreate,
            run=_create_goal,
            read_only=False,
        ),
        make_tool(
            name="update_savings_goal",
            description="Change a savings goal (name, target, deadline, status ACTIVE/ACHIEVED/ARCHIVED).",
            params=_with_id(SavingsGoalUpdate, "goal_id", "savings goal"),
            run=_update_goal,
            read_only=False,
        ),
        make_tool(
            name="add_to_savings_goal",
            description="Put money into (or take it out of, with a negative amount) a savings goal.",
            params=_AddSavings,
            run=_add_savings,
            read_only=False,
        ),
        make_tool(
            name="delete_savings_goal",
            description="Delete a savings goal.",
            params=_GoalId,
            run=_delete_goal,
            read_only=False,
            destructive=True,
        ),
    ]
