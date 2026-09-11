from ipo_edge.v11_candidate import institutional_demand_lane


def test_lane_triggers_only_with_verified_critical_evidence():
    scores = {"institutional_conviction": 0.90, "market_demand": 0.85}
    result = institutional_demand_lane(scores, critical_evidence_verified=True)
    assert result.lane_triggered is True
    assert result.actionable_candidate is True


def test_lane_does_not_override_nv_gate():
    scores = {"institutional_conviction": 1.0, "market_demand": 1.0}
    result = institutional_demand_lane(scores, critical_evidence_verified=False)
    assert result.actionable_candidate is False
    assert result.reason == "CRITICAL_EVIDENCE_NOT_VERIFIED"


def test_lane_does_not_override_hard_blocker():
    scores = {"institutional_conviction": 1.0, "market_demand": 1.0}
    result = institutional_demand_lane(scores, critical_evidence_verified=True, hard_blocker="GOVERNANCE")
    assert result.actionable_candidate is False


def test_lane_thresholds_are_exact():
    scores = {"institutional_conviction": 0.85, "market_demand": 0.80}
    assert institutional_demand_lane(scores, critical_evidence_verified=True).actionable_candidate is True
    scores = {"institutional_conviction": 0.8499, "market_demand": 0.80}
    assert institutional_demand_lane(scores, critical_evidence_verified=True).actionable_candidate is False
