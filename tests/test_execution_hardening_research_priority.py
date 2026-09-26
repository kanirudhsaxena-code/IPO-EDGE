import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "execution_hardening_research_priority.py"
spec = importlib.util.spec_from_file_location("execution_hardening_research_priority", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

research_priority = module.research_priority
preserve_disposition = module.preserve_disposition
research_priority_audit = module.research_priority_audit


def test_missing_critical_blocks_are_routed_before_noncritical_blocks():
    tasks = research_priority(["R5", "R4", "R1", "R7"])
    assert [task.block for task in tasks] == ["R4", "R7", "R1", "R5"]


def test_verified_strong_partial_signals_only_raise_retrieval_urgency():
    tasks = research_priority(
        ["R2", "R5", "R6"],
        verified_strong_partial_signals={"institutional": True, "demand": True},
    )
    assert [task.block for task in tasks[:2]] == ["R2", "R6"]
    assert all(task.priority == 0 for task in tasks[:2])
    assert tasks[-1].block == "R5"


def test_priority_router_does_not_create_model_signal_from_false_inputs():
    tasks = research_priority(
        ["R3", "R8"],
        verified_strong_partial_signals={"institutional": False, "demand": False},
    )
    assert tasks[0].block == "R3"
    assert tasks[0].priority == 1


def test_nv_and_hard_blocker_are_preserved_exactly():
    disposition, blocker = preserve_disposition(
        "NO_ACTION",
        hard_blocker="CRITICAL_EVIDENCE_NOT_VERIFIED",
    )
    assert disposition == "NO_ACTION"
    assert blocker == "CRITICAL_EVIDENCE_NOT_VERIFIED"


def test_audit_explicitly_reports_zero_model_policy_change():
    audit = research_priority_audit(
        ["R4", "R5"],
        verified_strong_partial_signals={"financials": True},
        disposition="NO_ACTION",
        hard_blocker="CRITICAL_EVIDENCE_NOT_VERIFIED",
    )
    assert audit["model_policy_changed"] is False
    assert audit["disposition"] == "NO_ACTION"
    assert audit["hard_blocker"] == "CRITICAL_EVIDENCE_NOT_VERIFIED"


def test_unknown_research_block_fails_closed():
    try:
        research_priority(["R9"])
    except ValueError as exc:
        assert "unknown research block" in str(exc)
    else:
        raise AssertionError("unknown block must fail closed")
