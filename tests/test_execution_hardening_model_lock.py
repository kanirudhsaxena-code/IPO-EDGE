from ipo_edge.scoring import WEIGHTS, calculate_score, grade_from_score
from ipo_edge.v11_candidate import institutional_demand_lane


FROZEN_WEIGHTS = {
    "business_quality": 15,
    "financial_quality": 15,
    "valuation": 20,
    "institutional_conviction": 20,
    "market_demand": 10,
    "analyst_consensus": 10,
    "sector_ipo_environment": 5,
    "gmp_confirmation": 5,
}


def test_execution_hardening_cannot_change_frozen_weights():
    assert WEIGHTS == FROZEN_WEIGHTS
    assert sum(WEIGHTS.values()) == 100


def test_execution_hardening_cannot_change_grade_thresholds_or_decisions():
    assert grade_from_score(95.00) == ("A++", "STRONG_SUBSCRIBE")
    assert grade_from_score(94.99) == ("A+", "SUBSCRIBE")
    assert grade_from_score(90.00) == ("A+", "SUBSCRIBE")
    assert grade_from_score(89.99) == ("A", "TRACK")
    assert grade_from_score(85.00) == ("A", "TRACK")
    assert grade_from_score(84.99) == ("REJECT", "REJECT")


def test_same_evidence_produces_identical_v11_output():
    evidence = {
        "business_quality": 0.90,
        "financial_quality": 0.80,
        "valuation": 0.75,
        "institutional_conviction": 0.90,
        "market_demand": 0.85,
        "analyst_consensus": 0.80,
        "sector_ipo_environment": 0.70,
        "gmp_confirmation": 0.60,
    }
    first = calculate_score(evidence, critical_evidence_verified=True)
    second = calculate_score(dict(evidence), critical_evidence_verified=True)
    assert first == second


def test_missing_critical_evidence_still_forces_nv_no_action():
    result = calculate_score({}, critical_evidence_verified=False)
    assert result.score is None
    assert result.grade == "NV"
    assert result.decision == "NO_ACTION"
    assert result.hard_blocker == "CRITICAL_EVIDENCE_NOT_VERIFIED"


def test_hard_blocker_still_forces_nv_no_action():
    result = calculate_score(
        {key: 1.0 for key in FROZEN_WEIGHTS},
        critical_evidence_verified=True,
        hard_blocker="GOVERNANCE",
    )
    assert result.score is None
    assert result.grade == "NV"
    assert result.decision == "NO_ACTION"
    assert result.hard_blocker == "GOVERNANCE"


def test_v11_institutional_demand_lane_does_not_bypass_nv():
    strong_signal = {"institutional_conviction": 1.0, "market_demand": 1.0}
    result = institutional_demand_lane(
        strong_signal,
        critical_evidence_verified=False,
    )
    assert result.actionable_candidate is False
    assert result.reason == "CRITICAL_EVIDENCE_NOT_VERIFIED"
