from __future__ import annotations

from app.knowledge.extraction import heuristic_extract, is_trivial
from app.knowledge.types import (
    ClaimType,
    Sensitivity,
    VerificationStatus,
    classify_sensitivity,
    contains_credential,
    normalize_entity_name,
    redact_credentials,
)


def test_credentials_are_detected_and_redacted():
    assert contains_credential("password: hunter2")
    assert contains_credential("api_key = sk-abcdefghijklmnopqrstuvwx")
    assert contains_credential("-----BEGIN RSA PRIVATE KEY-----")
    redacted = redact_credentials("my password: hunter2 and token=abcdefghijklmno")
    assert "hunter2" not in redacted
    assert "[redacted credential]" in redacted


def test_sensitivity_classification_is_explainable():
    assert classify_sensitivity("My salary is 100000", "topic") == Sensitivity.SENSITIVE.value
    assert classify_sensitivity("My doctor changed my medication", "topic") == Sensitivity.SENSITIVE.value
    assert classify_sensitivity("My sister lives in Pune", "topic") == Sensitivity.PERSONAL.value
    assert classify_sensitivity("The project uses React", "project") == Sensitivity.ORDINARY.value
    assert classify_sensitivity("password: abc", "topic") == Sensitivity.RESTRICTED.value


def test_entity_normalisation_is_stable():
    assert normalize_entity_name("  The IRIS   Project ") == "iris project"
    assert normalize_entity_name("IRIS-Project") == "iris-project"
    assert normalize_entity_name("!!!") == ""


def test_trivial_messages_are_ignored():
    assert is_trivial("hi")
    assert is_trivial("thanks")
    assert not is_trivial("My goal is to launch the IRIS knowledge system.")


def test_heuristic_extraction_preserves_claim_types_and_verification():
    result = heuristic_extract(
        "My goal is to launch IRIS. I think PostgreSQL is a good choice. "
        "We decided to use FastAPI for the backend.",
        origin="conversation",
    )
    types = {item["claim_type"] for item in result.items}
    assert ClaimType.FACT.value in types or ClaimType.DECISION.value in types
    decisions = [item for item in result.items if item["claim_type"] == ClaimType.DECISION.value]
    assert decisions
    assert decisions[0]["verification_status"] == VerificationStatus.USER_STATED.value
    inferences = [item for item in result.items if item["claim_type"] == ClaimType.INFERENCE.value]
    assert inferences
    assert inferences[0]["verification_status"] == VerificationStatus.INFERRED.value


def test_heuristic_extraction_excludes_credentials_only_text():
    result = heuristic_extract("password: hunter2\napi_key=sk-abcdefghijklmnopqrstuv", origin="user")
    assert not result.items
    assert result.excluded >= 1
