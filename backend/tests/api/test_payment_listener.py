"""Tests for /api/finance/auto-log payment notification endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models.finance import FinanceTransaction


def test_auto_log_payment_success(client: TestClient, db):
    payload = {
        "amount": 349.50,
        "merchant": "Swiggy Delivery",
        "raw_text": "Paid ₹349.50 to Swiggy Delivery using Google Pay UPI",
        "source": "gpay",
        "occurred_on": "2026-10-27",
    }
    res = client.post("/api/finance/auto-log", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "logged"
    assert data["transaction"]["amount"] == 349.50
    assert data["transaction"]["category"] == "Food & Dining"
    assert "Swiggy Delivery" in data["transaction"]["note"]

    # Verify database insertion
    tx = db.query(FinanceTransaction).filter(FinanceTransaction.id == data["transaction"]["id"]).first()
    assert tx is not None
    assert tx.category == "Food & Dining"


def test_auto_log_payment_deduplication(client: TestClient, db):
    payload = {
        "amount": 120.0,
        "merchant": "Zepto Groceries",
        "raw_text": "Paid ₹120 to Zepto Groceries",
        "source": "gpay",
        "occurred_on": "2026-10-27",
    }
    # First call -> logged
    res1 = client.post("/api/finance/auto-log", json=payload)
    assert res1.status_code == 200
    assert res1.json()["status"] == "logged"

    # Second call with same amount and merchant -> duplicate
    res2 = client.post("/api/finance/auto-log", json=payload)
    assert res2.status_code == 200
    assert res2.json()["status"] == "duplicate"
    assert res2.json()["transaction"]["id"] == res1.json()["transaction"]["id"]


def test_auto_log_payment_invalid_amount(client: TestClient, db):
    payload = {
        "amount": -50.0,
        "merchant": "Test",
        "source": "gpay",
    }
    res = client.post("/api/finance/auto-log", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"
