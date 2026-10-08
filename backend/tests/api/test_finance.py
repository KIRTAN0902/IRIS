"""Personal finance: API, summary math, bills, savings, IRIS's tools and situation."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.agent.registry import default_registry as registry
from app.models.user import User
from app.services import finance_service as fs


@pytest.fixture
def user(db, user_id) -> User:
    return db.get(User, user_id)


@pytest.fixture
def today(user) -> date:
    return fs.today_for(user)


def _tx(client, **body):
    r = client.post("/api/finance/transactions", json={"category": "Food & Dining", "amount": 100, **body})
    assert r.status_code == 201, r.text
    return r.json()


def test_transaction_crud_and_defaults(client, today):
    tx = _tx(client, amount=249.5, note="Lunch")
    assert tx["kind"] == "EXPENSE" and tx["account"] == "UPI"
    assert tx["occurred_on"] == today.isoformat() and tx["amount"] == 249.5

    r = client.patch(f"/api/finance/transactions/{tx['id']}", json={"amount": 300, "account": "CASH"})
    assert r.status_code == 200 and r.json()["amount"] == 300 and r.json()["account"] == "CASH"

    assert len(client.get("/api/finance/transactions").json()) == 1
    assert client.delete(f"/api/finance/transactions/{tx['id']}").status_code == 204
    assert client.get("/api/finance/transactions").json() == []
    assert client.delete(f"/api/finance/transactions/{tx['id']}").status_code == 404


@pytest.mark.parametrize("bad", [{"amount": 0}, {"amount": -5}, {"category": "   "}, {"kind": "LOAN"}])
def test_transaction_validation(client, bad):
    assert client.post("/api/finance/transactions", json={"category": "Food", "amount": 10, **bad}).status_code == 422


def test_summary_totals_categories_budgets(client, today):
    _tx(client, amount=500, category="Food & Dining")
    _tx(client, amount=1500, category="Food & Dining")
    _tx(client, amount=300, category="Transport")
    _tx(client, kind="INCOME", amount=20000, category="Stipend")
    # Last month is excluded from this month and counted as "previous".
    last_month = fs.add_months(today.replace(day=1), -1)
    _tx(client, amount=999, category="Shopping", occurred_on=last_month.isoformat())
    assert client.put("/api/finance/budgets", json={"category": "Food & Dining", "monthly_limit": 2500}).status_code == 200

    s = client.get("/api/finance/summary").json()
    assert (s["expense"], s["income"], s["net"]) == (2300, 20000, 17700)
    assert s["previous_month_expense"] == 999
    assert [(c["category"], c["amount"], c["budget"]) for c in s["by_category"]] == [
        ("Food & Dining", 2000, 2500),
        ("Transport", 300, None),
    ]
    food = s["budgets"][0]
    assert (food["spent"], food["remaining"], food["percent"]) == (2000, 500, 80)
    assert s["daily"][-1]["day"] == today.isoformat()
    assert len(s["recent"]) == 5

    other = client.get(f"/api/finance/summary?month={last_month:%Y-%m}").json()
    assert other["expense"] == 999 and other["month"] == f"{last_month:%Y-%m}"


def test_budget_upsert_and_delete(client):
    first = client.put("/api/finance/budgets", json={"category": "Groceries", "monthly_limit": 4000}).json()
    again = client.put("/api/finance/budgets", json={"category": "Groceries", "monthly_limit": 5000}).json()
    assert first["id"] == again["id"] and again["monthly_limit"] == 5000
    assert client.delete(f"/api/finance/budgets/{first['id']}").status_code == 204
    assert client.get("/api/finance/summary").json()["budgets"] == []


def test_paying_a_bill_logs_expense_and_rolls_due_date(client, today):
    bill = client.post(
        "/api/finance/bills",
        json={"name": "Rent", "amount": 12000, "category": "Rent", "next_due": "2026-01-31"},
    ).json()
    paid = client.post(f"/api/finance/bills/{bill['id']}/pay", json={}).json()
    assert paid["next_due"] == "2026-02-28"  # month-end clamps
    assert paid["last_paid_on"] == today.isoformat()
    txs = client.get("/api/finance/transactions").json()
    assert txs[0]["bill_id"] == bill["id"] and txs[0]["amount"] == 12000 and txs[0]["category"] == "Rent"

    once = client.post(
        "/api/finance/bills",
        json={"name": "Course fee", "amount": 5000, "frequency": "ONCE", "next_due": today.isoformat()},
    ).json()
    done = client.post(f"/api/finance/bills/{once['id']}/pay", json={"amount": 4500}).json()
    assert done["active"] is False
    assert client.get("/api/finance/transactions").json()[0]["amount"] == 4500
    assert client.post(f"/api/finance/bills/{once['id']}/pay", json={}).status_code == 422


def test_bills_due_window_in_summary(client, today):
    client.post("/api/finance/bills", json={"name": "Netflix", "amount": 199, "next_due": (today + timedelta(days=3)).isoformat()})
    client.post("/api/finance/bills", json={"name": "Insurance", "amount": 9000, "frequency": "YEARLY", "next_due": (today + timedelta(days=200)).isoformat()})
    due = client.get("/api/finance/summary").json()["bills_due"]
    assert [(b["name"], b["days_until_due"]) for b in due] == [("Netflix", 3)]


def test_savings_goal_progress_and_achievement(client):
    goal = client.post("/api/finance/savings", json={"name": "Laptop", "target_amount": 80000}).json()
    assert goal["status"] == "ACTIVE" and goal["percent"] == 0
    goal = client.post(f"/api/finance/savings/{goal['id']}/add", json={"amount": 60000}).json()
    assert goal["percent"] == 75
    goal = client.post(f"/api/finance/savings/{goal['id']}/add", json={"amount": 25000}).json()
    assert goal["status"] == "ACHIEVED" and goal["percent"] == 100
    goal = client.post(f"/api/finance/savings/{goal['id']}/add", json={"amount": -90000}).json()
    assert goal["saved_amount"] == 0 and goal["status"] == "ACTIVE"


def test_inr_formatting():
    assert fs.inr(123456.5) == "₹1,23,456.50"
    assert fs.inr(999) == "₹999"
    assert fs.inr(10000000) == "₹1,00,00,000"
    assert fs.inr(-2500) == "-₹2,500"


async def test_agent_logs_and_pays_through_tools(db, user, today):
    res = await registry.execute("log_transaction", db, user, {"amount": 250, "category": "Food & Dining", "note": "lunch"})
    assert res.success, res.error
    assert "₹250 Food & Dining (UPI" in res.summary

    res = await registry.execute(
        "create_bill", db, user, {"name": "Jio recharge", "amount": 349, "next_due": today.isoformat()}
    )
    assert res.success, res.error
    bill_id = res.data["id"]
    res = await registry.execute("pay_bill", db, user, {"bill_id": bill_id})
    assert res.success and "Paid Jio recharge (₹349)" in res.summary

    res = await registry.execute("set_budget", db, user, {"category": "Food & Dining", "monthly_limit": 300})
    assert res.success
    summary = await registry.execute("get_finances", db, user, {})
    assert summary.data["expense"] == 599

    ids = [t["id"] for t in summary.data["recent"]]
    res = await registry.execute("delete_transactions", db, user, {"transaction_ids": [*ids, 99999]})
    assert res.data == {"deleted": ids, "not_found": [99999]}


def test_situation_mentions_due_bills_and_tight_budgets(db, user, today):
    from app.intelligence.situation import build_situation, render_situation
    from app.schemas.finance import BillCreate, TransactionCreate

    assert build_situation(db, user)["money"] is None  # nothing tracked yet: no noise

    fs.create_bill(db, user, BillCreate(name="Rent", amount=12000, category="Rent", next_due=today + timedelta(days=1)))
    fs.set_budget(db, user, "Food & Dining", 1000)
    fs.create_transaction(db, user, TransactionCreate(amount=950, category="Food & Dining"))
    text = render_situation(build_situation(db, user))
    assert "MONEY" in text and "spent ₹950" in text
    assert "Rent ₹12,000" in text and "(in 1d)" in text
    assert "Budget Food & Dining: 95% used (₹50 left)" in text
