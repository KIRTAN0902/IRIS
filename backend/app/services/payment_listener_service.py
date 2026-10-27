"""Automatic payment notification processing and categorization for IRIS Finance."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import re

from sqlalchemy.orm import Session

from app.models.enums import PaymentAccount, TransactionKind
from app.models.finance import FinanceTransaction
from app.models.user import User
from app.schemas.finance import AutoLogPaymentRequest, AutoLogPaymentResponse, TransactionOut
from app.services import finance_service as fs

# Smart category keyword mapping for Indian UPI merchants
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Food & Dining": [
        "swiggy", "zomato", "starbucks", "mcdonald", "burger", "pizza",
        "cafe", "restaurant", "canteen", "tea", "chai", "dhaba",
        "subway", "dominos", "kfc", "eats", "bakery", "sweets", "coffee",
        "barbeque", "bikanervala", "haldiram"
    ],
    "Groceries": [
        "zepto", "blinkit", "instamart", "supermarket", "grocery",
        "bigbasket", "dmart", "reliance fresh", "spencer", "kirana",
        "milk", "fruits", "vegetables", "nature basket", "dunzo", "store"
    ],
    "Transport": [
        "uber", "ola", "rapido", "metro", "auto", "petrol", "fuel",
        "diesel", "hpcl", "bpcl", "iocl", "shell", "parking", "toll",
        "fastag", "irctc", "railway", "redbus", "flight", "indigo"
    ],
    "Shopping": [
        "amazon", "flipkart", "myntra", "zara", "h&m", "ajio", "meesho",
        "nykaa", "croma", "reliance digital", "apple", "retail", "mart"
    ],
    "Bills & Utilities": [
        "bescom", "electricity", "water", "wifi", "broadband", "airtel",
        "jio", "vi ", "gas", "cylinder", "bill", "recharge", "utility"
    ],
    "Subscriptions": [
        "youtube", "chatgpt", "openai", "github", "cursor", "icloud",
        "google storage", "spotify", "prime", "hotstar"
    ],
    "Entertainment": [
        "bookmyshow", "pvr", "inox", "cinema", "netflix", "movie", "gaming", "steam"
    ],
    "Health": [
        "pharmacy", "apollo", "1mg", "pharmeasy", "hospital", "clinic",
        "medical", "lab", "dr ", "doctor", "dentist", "medplus"
    ],
}


def guess_category(merchant: str, raw_text: str | None = None) -> str:
    """Guess the transaction category from the merchant name or raw notification text."""
    combined = f"{merchant} {raw_text or ''}".lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return category
    return "Other"


def process_auto_payment(db: Session, user: User, payload: AutoLogPaymentRequest) -> AutoLogPaymentResponse:
    """Process an incoming payment notification from Android (GPay / PhonePe / etc.)."""
    occurred_date = payload.occurred_on or fs.today_for(user)
    amount_dec = Decimal(str(round(payload.amount, 2)))

    if amount_dec <= Decimal("0"):
        return AutoLogPaymentResponse(
            status="ignored",
            message="Payment amount must be greater than zero.",
            transaction=None,
        )

    clean_merchant = payload.merchant.strip() or "UPI Payment"
    category = payload.category or guess_category(clean_merchant, payload.raw_text)

    # 1. Deduplication check: Avoid logging the same payment if sent twice within the same day
    existing = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.user_id == user.id,
            FinanceTransaction.occurred_on == occurred_date,
            FinanceTransaction.amount == amount_dec,
            FinanceTransaction.kind == TransactionKind.EXPENSE.value,
        )
        .first()
    )

    if existing and (
        clean_merchant.lower() in (existing.note or "").lower()
        or (existing.note or "").lower() in clean_merchant.lower()
    ):
        return AutoLogPaymentResponse(
            status="duplicate",
            message=f"Transaction of ₹{amount_dec} for '{clean_merchant}' already recorded.",
            transaction=TransactionOut.model_validate(existing),
        )

    # 2. Insert new transaction
    tx = FinanceTransaction(
        user_id=user.id,
        kind=TransactionKind.EXPENSE.value,
        amount=amount_dec,
        category=category,
        account=payload.account.value if hasattr(payload.account, "value") else str(payload.account),
        occurred_on=occurred_date,
        note=f"{clean_merchant} (Auto: {payload.source})",
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)

    return AutoLogPaymentResponse(
        status="logged",
        message=f"Logged ₹{amount_dec} for '{clean_merchant}' under '{category}'.",
        transaction=TransactionOut.model_validate(tx),
    )
