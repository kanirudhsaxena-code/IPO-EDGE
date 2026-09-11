from datetime import datetime, timezone, timedelta
from ipo_edge.evidence import EvidenceItem, filter_for_checkpoint
from ipo_edge.pipeline import classify_outcome


def test_post_checkpoint_evidence_is_excluded():
    t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    before = EvidenceItem("R2", "x", "ok", "https://nseindia.com/a", "NSE", t - timedelta(hours=2), numeric_value=0.8)
    after = EvidenceItem("R2", "x", "late", "https://nseindia.com/b", "NSE", t + timedelta(hours=2), numeric_value=0.9)
    assert filter_for_checkpoint([before, after], t) == [before]


def test_outcome_classification():
    assert classify_outcome("A+", 25) == "STRONG_HIT"
    assert classify_outcome("A+", 10) == "MODERATE_HIT"
    assert classify_outcome("A+", -2) == "FALSE_POSITIVE"
    assert classify_outcome("A", 25) == "MISSED_OPPORTUNITY"
    assert classify_outcome("REJECT", 5) == "CORRECT_AVOIDANCE"
