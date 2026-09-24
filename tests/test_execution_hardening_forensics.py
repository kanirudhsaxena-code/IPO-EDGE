from scripts.execution_hardening_forensics import CAUSES, classify


def row(**kwargs):
    base = {"run_errors": None, "hard_blocker": None, "missed_signal_summary": None,
            "critical_missing": 0, "not_verified": 0, "classification": None, "grade": "NV"}
    base.update(kwargs)
    return base


def test_classifier_taxonomy_is_frozen_execution_only():
    assert CAUSES == {"RETRIEVAL","IDENTITY","TIMING","CONFLICT","UNIVERSE","INFRASTRUCTURE","MODEL_RELATED_DEFERRED","UNRESOLVED"}


def test_specific_execution_causes_precede_generic_retrieval():
    assert classify(row(hard_blocker="duplicate alias identity", critical_missing=2)) == "IDENTITY"
    assert classify(row(hard_blocker="final day T2 timing failure", critical_missing=2)) == "TIMING"
    assert classify(row(hard_blocker="source conflict", critical_missing=2)) == "CONFLICT"
    assert classify(row(hard_blocker="universe discovery missing IPO", critical_missing=2)) == "UNIVERSE"
    assert classify(row(hard_blocker="HTTP 403 blocked", critical_missing=2)) == "INFRASTRUCTURE"


def test_missing_verified_critical_evidence_is_retrieval():
    assert classify(row(critical_missing=1)) == "RETRIEVAL"
    assert classify(row(not_verified=1)) == "RETRIEVAL"


def test_model_related_miss_is_deferred_not_changed():
    assert classify(row(classification="MISSED_OPPORTUNITY", grade="A")) == "MODEL_RELATED_DEFERRED"


def test_no_evidence_for_cause_remains_unresolved():
    assert classify(row()) == "UNRESOLVED"
