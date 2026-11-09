"""Notification Intelligence & GPay Ingestion Service for Notification Coworker.

STRICT OWNERSHIP BOUNDARY:
- Notification Coworker is an event-ingestion specialist, NOT the financial manager.
- Flow: Notification -> Structured Transaction Event -> IRIS Core -> Financial Processing.
- IRIS Core owns: transaction categorisation, financial records, budgets, summaries, insights.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.user import User
from app.schemas.finance import AutoLogPaymentRequest, AutoLogPaymentResponse
from app.services import payment_listener_service as pls

logger = get_logger("iris.services.notification_coworker")

# Recognized payment package IDs for local filtering
ALLOWED_PAYMENT_PACKAGES = {
    "com.google.android.apps.nbu.paisa.user",  # Google Pay (India/Tez)
    "com.google.android.apps.walletnfcrel",   # Google Wallet / Pay
    "com.phonepe.app",                        # PhonePe
    "net.one97.paytm",                        # Paytm
    "com.dreamplug.androidapp",               # CRED
    "in.org.npci.upiapp",                     # BHIM
}

# Transaction statuses recognized
VALID_STATUSES = {"completed", "pending", "failed", "reversed"}


class IngestNotificationPayload(BaseModel):
    package_name: str = Field(..., description="Android app package name, e.g. com.google.android.apps.nbu.paisa.user")
    title: str = Field("", description="Notification title")
    text: str = Field(..., description="Notification body text")
    amount: float | None = Field(None, description="Extracted amount if pre-parsed")
    currency: str = Field("INR", description="Currency symbol or code (default: INR)")
    direction: str = Field("debit", description="debit, credit, or status")
    merchant: str | None = Field(None, description="Extracted counterparty or merchant")
    transaction_ref: str | None = Field(None, description="UPI RRN, UTR, or reference number")
    status: str = Field("completed", description="completed, pending, failed, reversed")
    timestamp: datetime | None = Field(None, description="Event timestamp")


class NotificationEventRecordOut(BaseModel):
    id: str
    package_name: str
    merchant: str
    amount: float
    currency: str
    direction: str
    status: str
    transaction_ref: str | None
    forwarded_to_core: bool
    core_response: str | None
    created_at: datetime


class NotificationCoworkerService:
    """Specialized engine for ingesting, validating, and forwarding GPay notifications to IRIS Core."""

    def __init__(self) -> None:
        self._recent_events: list[dict[str, Any]] = []
        self._seen_refs: set[str] = set()

    def is_listener_active(self, db: Session, user_id: int) -> bool:
        """Check whether Android notification listener has ever reported or active device exists."""
        if len(self._recent_events) > 0:
            return True

        try:
            from app.models.mesh_pairing import MeshPairing

            dev = (
                db.query(MeshPairing)
                .filter(
                    MeshPairing.user_id == user_id,
                    MeshPairing.is_active.is_(True),
                    MeshPairing.device_type.ilike("%phone%") | MeshPairing.device_type.ilike("%android%"),
                )
                .first()
            )
            if dev is not None:
                return True
        except Exception:
            pass

        try:
            from app.models.finance import FinanceTransaction

            has_auto_txn = (
                db.query(FinanceTransaction)
                .filter(
                    FinanceTransaction.user_id == user_id,
                    FinanceTransaction.note.ilike("%Auto: gpay%"),
                )
                .first()
                is not None
            )
            if has_auto_txn:
                return True
        except Exception:
            pass

        return False

    def get_status(self, db: Session, user_id: int) -> dict[str, Any]:
        """Return genuine setup and listener status."""
        active = self.is_listener_active(db, user_id)
        return {
            "is_active": active,
            "status": "ready" if active else "needs_setup",
            "message": (
                "Android notification listener is active and monitoring GPay transactions."
                if active
                else "Needs setup: Grant notification-listener permission on your Android device in IRIS Settings."
            ),
            "events_ingested_count": len(self._recent_events),
            "supported_apps": ["Google Pay (GPay / Tez)", "Google Wallet", "PhonePe", "Paytm", "BHIM"],
        }

    def get_recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recently ingested notification events."""
        return self._recent_events[-limit:][::-1]

    def ingest_event(
        self,
        db: Session,
        user: User,
        payload: IngestNotificationPayload,
    ) -> dict[str, Any]:
        """Validate, filter, and forward structured GPay transaction event to IRIS Core."""
        pkg = payload.package_name.strip()
        lower_body = (payload.title + " " + payload.text).lower()

        # 1. Privacy & Scope Filter: Ensure event is from a supported payment app
        is_payment_pkg = pkg in ALLOWED_PAYMENT_PACKAGES or any(p in pkg for p in ("paisa", "wallet", "pay"))
        has_payment_indicator = any(k in lower_body for k in ("paid", "debited", "sent", "received", "credited", "upi", "inr", "₹", "rs"))

        if not is_payment_pkg and not has_payment_indicator:
            logger.info("Dropping non-payment notification from %s for privacy", pkg)
            return {
                "accepted": False,
                "status": "filtered",
                "message": "Notification is not a recognized payment event. Dropped locally for privacy.",
            }

        # 2. Extract or Normalize Amount
        amount = payload.amount
        if amount is None or amount <= 0:
            amt_match = re.search(r"(?:₹|rs\.?|inr)\s*([0-9,]+(?:\.[0-9]{1,2})?)", lower_body, re.IGNORECASE)
            if amt_match:
                amount_str = amt_match.group(1).replace(",", "")
                try:
                    amount = float(amount_str)
                except ValueError:
                    amount = 0.0
            else:
                amount = 0.0

        if amount <= 0:
            return {
                "accepted": False,
                "status": "ignored",
                "message": "No valid transaction amount detected in notification.",
            }

        # 3. Extract or Normalize Merchant / Counterparty
        merchant = payload.merchant
        if not merchant or not merchant.strip():
            raw_text = payload.title + " " + payload.text
            m_match = re.search(
                r"(?:paid to|sent to|transfer to|payment to|to|at|from)\s+([^.,\n\r]+?)(?:\s+using|\s+via|\s+on|\s+for|\s+with|\s+ref|\.|$)",
                raw_text,
                re.IGNORECASE,
            )
            merchant = m_match.group(1).strip() if m_match else "GPay Merchant"

        # 4. Extract or Normalize Reference / UTR
        ref = payload.transaction_ref
        if not ref or not ref.strip():
            ref_match = re.search(r"(?:ref|rrn|utr|txn\s*id|transaction\s*id)[:\s]*([0-9a-zA-Z]{10,24})", lower_body, re.IGNORECASE)
            ref = ref_match.group(1).strip() if ref_match else None

        # 5. Determine Transaction Direction & Status
        raw_status = payload.status.lower()
        if raw_status not in VALID_STATUSES:
            raw_status = "completed"

        if any(w in lower_body for w in ("failed", "declined", "unsuccessful")):
            raw_status = "failed"
        elif any(w in lower_body for w in ("pending", "processing", "initiated")):
            raw_status = "pending"
        elif any(w in lower_body for w in ("reversed", "refunded")):
            raw_status = "reversed"

        direction = payload.direction.lower()
        if any(w in lower_body for w in ("received", "credited", "refund")):
            direction = "credit"
        else:
            direction = "debit"

        # 6. Deduplication Check
        event_key = f"{ref}:{amount}:{merchant}:{direction}" if ref else f"{amount}:{merchant}:{direction}"
        if event_key in self._seen_refs:
            return {
                "accepted": True,
                "status": "duplicate",
                "message": f"Duplicate GPay event detected for '{merchant}' ({payload.currency} {amount}). Skipped.",
                "forwarded_to_core": False,
            }
        self._seen_refs.add(event_key)

        # 7. Forward to IRIS Core Financial Processing (Strict Ownership Boundary)
        core_message = None
        forwarded = False
        if raw_status == "completed":
            core_req = AutoLogPaymentRequest(
                amount=amount,
                merchant=merchant,
                direction="income" if direction == "credit" else "expense",
                account="UPI",
                source="gpay",
                transaction_ref=ref,
                raw_text=payload.text,
            )
            core_resp: AutoLogPaymentResponse = pls.process_auto_payment(db, user, core_req)
            core_message = core_resp.message
            forwarded = True
        else:
            core_message = f"Transaction has status '{raw_status}'. Not recorded as a settled financial record."

        # 8. Record structured event in Notification Coworker event history
        event_id = f"notif-evt-{len(self._recent_events) + 1}"
        record = {
            "id": event_id,
            "package_name": pkg,
            "merchant": merchant,
            "amount": amount,
            "currency": payload.currency or "INR",
            "direction": direction,
            "status": raw_status,
            "transaction_ref": ref,
            "forwarded_to_core": forwarded,
            "core_response": core_message,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._recent_events.append(record)

        return {
            "accepted": True,
            "status": "processed",
            "event_id": event_id,
            "structured_event": record,
            "forwarded_to_core": forwarded,
            "core_response": core_message,
        }


notification_coworker_service = NotificationCoworkerService()
