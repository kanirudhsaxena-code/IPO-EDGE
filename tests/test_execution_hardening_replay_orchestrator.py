import importlib.util
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("eh_replay_orchestrator", SCRIPTS / "execution_hardening_replay_orchestrator.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def payload():
    case = {"case_id":"1","checkpoint_at":"2026-01-01T19:00:00+05:30","evidence_as_of":"2026-01-01T18:59:00+05:30","evidence_fingerprint":"e1","score":75,"grade":"A","decision":"TRACK","outcome_fingerprint":"o1","retrieval_nv":True}
    shadow = {"case_id":"1","evidence_as_of":"2026-01-01T18:59:00+05:30","evidence_fingerprint":"e1","score":75,"grade":"A","decision":"TRACK","canonical_outcome_fingerprint":"o1","retrieval_nv":False}
    return {"frozen_cases":[case], "shadow_results":[shadow]}


def test_valid_replay_is_execution_only():
    out = mod.run(payload())
    assert out["population"] == 1
    assert out["validation"]["checked"] == 1
    assert out["execution_deltas"]["retrieval_nv"] == 1
    assert out["canonical_history_mutated"] is False
    assert out["model_rules_changed"] is False


def test_future_evidence_fails_closed():
    p = payload(); p["shadow_results"][0]["evidence_as_of"] = "2026-01-01T19:01:00+05:30"
    with pytest.raises(ValueError, match="future-data leakage"):
        mod.run(p)


def test_identical_evidence_output_drift_fails_closed():
    p = payload(); p["shadow_results"][0]["grade"] = "B"
    with pytest.raises(AssertionError, match="model-rule drift"):
        mod.run(p)


def test_history_mutation_fails_closed():
    p = payload(); p["shadow_results"][0]["canonical_outcome_fingerprint"] = "changed"
    with pytest.raises(AssertionError, match="historical outcome mutation"):
        mod.run(p)


def test_population_mismatch_fails_closed():
    p = payload(); p["shadow_results"] = []
    with pytest.raises(ValueError, match="population mismatch"):
        mod.run(p)
