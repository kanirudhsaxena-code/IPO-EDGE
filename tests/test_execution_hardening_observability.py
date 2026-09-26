import pytest
from scripts.execution_hardening_observability import IPODiagnostic, build_execution_diagnostics, canonical_efficacy_view


def test_diagnostics_expose_counts_ipo_details_and_provider_health():
    ipo = IPODiagnostic("IPO-1", ("R2", "R4"), ("NSE", "SEBI"), ("R2 conflict",), "RESOLVED", "NV")
    out = build_execution_diagnostics(expected=2, reconciled=2, researched=1, ipos=[ipo], source_health={"NSE": "OK", "SEBI": "OK"}, upstox_available=False)
    assert out["counts"] == {"expected": 2, "reconciled": 2, "researched": 1, "complete": 0, "nv": 1, "partial": 0}
    assert out["ipos"][0]["unresolved_blocks"] == ("R2", "R4")
    assert out["ipos"][0]["attempted_sources"] == ("NSE", "SEBI")
    assert out["ipos"][0]["conflicts"] == ("R2 conflict",)
    assert out["ipos"][0]["identity_status"] == "RESOLVED"
    assert out["provider_health"]["upstox_available"] is False
    assert out["framework_efficacy"] is None
    assert out["model_policy_changed"] is False


def test_canonical_efficacy_is_separate_from_execution_diagnostics():
    view = canonical_efficacy_view({"decision_accuracy_pct": 68.6})
    assert view["kind"] == "CANONICAL_EFFICACY"
    assert view["execution_diagnostics"] is None
    assert view["efficacy"]["decision_accuracy_pct"] == 68.6


def test_fail_closed_on_impossible_counts():
    with pytest.raises(ValueError):
        build_execution_diagnostics(expected=1, reconciled=2, researched=1, ipos=[], source_health={}, upstox_available=False)


def test_fail_closed_on_unknown_disposition():
    with pytest.raises(ValueError):
        IPODiagnostic("IPO-1", (), (), (), "RESOLVED", "BUY")
