from __future__ import annotations


def learning_candidate(company_name: str, classification: str, missed_signal_summary: str | None = None) -> dict | None:
    if classification not in {"MISSED_OPPORTUNITY", "FALSE_POSITIVE"}:
        return None
    direction = "missed winner" if classification == "MISSED_OPPORTUNITY" else "false positive"
    return {
        "origin_company": company_name,
        "observed_signal": missed_signal_summary or direction,
        "hypothesis": f"Review whether a reproducible pre-listing signal explains this {direction}",
        "development_result": None,
        "validation_result": None,
        "status": "TESTING",
        "proposed_change": None,
    }


def can_adopt(learning: dict) -> bool:
    return (
        learning.get("status") == "VALIDATED"
        and learning.get("development_result") is not None
        and learning.get("validation_result") is not None
        and bool(learning.get("proposed_change"))
    )
