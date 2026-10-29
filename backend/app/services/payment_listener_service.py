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
    """Process an incoming payment notification from Android (GPay / PhonePe / Paytm / SMS)."""
    occurred_date = payload.occurred_on or fs.today_for(user)
    amount_dec = Decimal(str(round(payload.amount, 2)))

    if amount_dec <= Decimal("0"):
        return AutoLogPaymentResponse(
            status="ignored",
            message="Payment amount must be greater than zero.",
            transaction=None,
        )

    # Ignore failed or pending non-settled alerts
    direction_normalized = (payload.direction or "expense").strip().lower()
    if direction_normalized in ("failed", "declined", "unsuccessful", "pending", "cancelled"):
        return AutoLogPaymentResponse(
            status="ignored",
            message=f"Transaction with status '{payload.direction}' ignored.",
            transaction=None,
        )

    is_income = direction_normalized in ("income", "credit", "received", "refund")
    kind = TransactionKind.INCOME.value if is_income else TransactionKind.EXPENSE.value

    clean_merchant = payload.merchant.strip() or ("Received Money" if is_income else "UPI Payment")
    category = payload.category
    if not category:
        category = guess_category(clean_merchant, payload.raw_text)
        if category == "Other" and is_income:
            category = "Refund & Reimbursements" if "refund" in direction_normalized else "Other Income"

    # 1. Deduplication by explicit Transaction Reference (UPI RRN / UTR / Txn ID) if present
    if payload.transaction_ref and payload.transaction_ref.strip():
        ref_clean = payload.transaction_ref.strip()
        existing_ref = (
            db.query(FinanceTransaction)
            .filter(
                FinanceTransaction.user_id == user.id,
                FinanceTransaction.note.ilike(f"%{ref_clean}%"),
            )
            .first()
        )
        if existing_ref:
            return AutoLogPaymentResponse(
                status="duplicate",
                message=f"Transaction with reference '{ref_clean}' already recorded.",
                transaction=TransactionOut.model_validate(existing_ref),
            )

    # 2. Deduplication check: Avoid logging the same payment if sent twice within the same day
    existing = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.user_id == user.id,
            FinanceTransaction.occurred_on == occurred_date,
            FinanceTransaction.amount == amount_dec,
            FinanceTransaction.kind == kind,
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

    # Construct clean, privacy-safe note
    note_parts = [f"{clean_merchant} (Auto: {payload.source})"]
    if payload.transaction_ref and payload.transaction_ref.strip():
        note_parts.append(f"[Ref: {payload.transaction_ref.strip()}]")
    if direction_normalized in ("refund", "income"):
        note_parts.append(f"({direction_normalized.title()})")
    note = " ".join(note_parts)[:255]

    # 3. Insert new transaction
    tx = FinanceTransaction(
        user_id=user.id,
        kind=kind,
        amount=amount_dec,
        category=category,
        account=payload.account.value if hasattr(payload.account, "value") else str(payload.account),
        occurred_on=occurred_date,
        note=note,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)

    action_verb = "Credited" if is_income else "Logged"
    return AutoLogPaymentResponse(
        status="logged",
        message=f"{action_verb} ₹{amount_dec} for '{clean_merchant}' under '{category}'.",
        transaction=TransactionOut.model_validate(tx),
    )
