"""Personal finance endpoints: transactions, budgets, bills, savings goals and a monthly summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models.enums import TransactionKind
from app.models.user import User
from app.schemas.finance import (
    BillCreate,
    BillOut,
    BillPay,
    BillUpdate,
    BudgetOut,
    BudgetSet,
    Categories,
    FinanceSummary,
    SavingsContribution,
    SavingsGoalCreate,
    SavingsGoalOut,
    SavingsGoalUpdate,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
)
from app.services import finance_service as fs

router = APIRouter(prefix="/finance", tags=["finance"])

Month = Query(None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM (default: this month)")


@router.get("/summary", response_model=FinanceSummary)
def get_summary(month: str | None = Month, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return fs.summary(db, user, month)


@router.get("/categories", response_model=Categories)
def get_categories(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Default categories plus any custom ones the user has used."""
    used = {t.category: t.kind for t in fs.list_transactions(db, user, limit=1000)}
    custom = lambda kind, base: base + sorted(c for c, k in used.items() if k == kind and c not in base)  # noqa: E731
    return Categories(
        expense=custom(TransactionKind.EXPENSE.value, fs.EXPENSE_CATEGORIES),
        income=custom(TransactionKind.INCOME.value, fs.INCOME_CATEGORIES),
    )


# --- Transactions ---------------------------------------------------------------------


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    month: str | None = Month,
    kind: TransactionKind | None = None,
    category: str | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(300, ge=1, le=1000),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return fs.list_transactions(
        db, user, month=month, kind=kind.value if kind else None, category=category, search=q, limit=limit
    )


@router.post("/transactions", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(data: TransactionCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return fs.create_transaction(db, user, data)


@router.patch("/transactions/{tx_id}", response_model=TransactionOut)
def update_transaction(
    tx_id: int, data: TransactionUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return fs.update_transaction(db, user, tx_id, data)


@router.delete("/transactions/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(tx_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    fs.delete_transaction(db, user, tx_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Budgets ------------------------------------------------------------------------------


@router.put("/budgets", response_model=BudgetOut)
def set_budget(data: BudgetSet, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Create or change the monthly limit for a category."""
    return fs.set_budget(db, user, data.category, data.monthly_limit)


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(budget_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    fs.delete_budget(db, user, budget_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Bills -------------------------------------------------------------------------------


@router.get("/bills", response_model=list[BillOut])
def list_bills(user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = fs.today_for(user)
    return [fs.bill_out(b, today) for b in fs.list_bills(db, user)]


@router.post("/bills", response_model=BillOut, status_code=status.HTTP_201_CREATED)
def create_bill(data: BillCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return fs.bill_out(fs.create_bill(db, user, data), fs.today_for(user))


@router.patch("/bills/{bill_id}", response_model=BillOut)
def update_bill(bill_id: int, data: BillUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return fs.bill_out(fs.update_bill(db, user, bill_id, data), fs.today_for(user))


@router.post("/bills/{bill_id}/pay", response_model=BillOut)
def pay_bill(bill_id: int, data: BillPay | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Log the payment as an expense and roll the bill to its next due date."""
    data = data or BillPay()
    bill, _ = fs.pay_bill(db, user, bill_id, paid_on=data.paid_on, amount=data.amount)
    return fs.bill_out(bill, fs.today_for(user))


@router.delete("/bills/{bill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bill(bill_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    fs.delete_bill(db, user, bill_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Savings goals ---------------------------------------------------------------------------


@router.get("/savings", response_model=list[SavingsGoalOut])
def list_savings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [fs.savings_out(g) for g in fs.list_savings_goals(db, user)]


@router.post("/savings", response_model=SavingsGoalOut, status_code=status.HTTP_201_CREATED)
def create_savings(data: SavingsGoalCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return fs.savings_out(fs.create_savings_goal(db, user, data))


@router.patch("/savings/{goal_id}", response_model=SavingsGoalOut)
def update_savings(
    goal_id: int, data: SavingsGoalUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return fs.savings_out(fs.update_savings_goal(db, user, goal_id, data))


@router.post("/savings/{goal_id}/add", response_model=SavingsGoalOut)
def add_to_savings(
    goal_id: int, data: SavingsContribution, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return fs.savings_out(fs.add_to_savings_goal(db, user, goal_id, data.amount))


@router.delete("/savings/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_savings(goal_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    fs.delete_savings_goal(db, user, goal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
