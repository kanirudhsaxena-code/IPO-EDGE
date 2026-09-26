from datetime import datetime, timezone
import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "execution_hardening_shadow_replay.py"
spec = importlib.util.spec_from_file_location("execution_hardening_shadow_replay", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

FrozenCase = mod.FrozenCase
ShadowResult = mod.ShadowResult


def dt(hour):
    return datetime(2026, 1, 10, hour, tzinfo=timezone.utc)


def pair(**shadow_overrides):
    case = FrozenCase("ipo-1", dt(12), dt(11), "ev-1", 71, "A", "TRACK", "out-1")
    values = dict(case_id="ipo-1", evidence_as_of=dt(11), evidence_fingerprint="ev-1",
                  score=71, grade="A", decision="TRACK",
                  canonical_outcome_fingerprint="out-1")
    values.update(shadow_overrides)
    return case, ShadowResult(**values)


def test_same_evidence_same_output_passes():
    case, shadow = pair()
    mod.replay_guard(case, shadow)


def test_same_evidence_changed_output_is_model_drift():
    case, shadow = pair(decision="APPLY")
    try:
        mod.replay_guard(case, shadow)
        assert False, "expected model drift failure"
    except AssertionError as exc:
        assert "model-rule drift" in str(exc)


def test_future_evidence_fails_closed():
    case, shadow = pair(evidence_as_of=dt(13))
    try:
        mod.replay_guard(case, shadow)
        assert False, "expected future evidence failure"
    except ValueError as exc:
        assert "future-data leakage" in str(exc)


def test_history_fingerprint_cannot_change():
    case, shadow = pair(canonical_outcome_fingerprint="rewritten")
    try:
        mod.replay_guard(case, shadow)
        assert False, "expected immutable-history failure"
    except AssertionError as exc:
        assert "historical outcome mutation" in str(exc)


def test_model_related_miss_is_deferred_only():
    case, shadow = pair(model_related_miss=True)
    assert mod.classify_miss(shadow) == mod.MODEL_RELATED_DEFERRED


def test_execution_delta_metrics_exclude_model_policy():
    before = [{"retrieval_nv": True, "partial": True, "identity_error": True,
               "universe_gap": True, "missed_t2": True, "model_related_miss": True}]
    after = [{"retrieval_nv": False, "partial": False, "identity_error": False,
              "universe_gap": False, "missed_t2": False, "model_related_miss": False}]
    result = mod.measure_execution_deltas(before, after)
    assert result == {"retrieval_nv": 1, "partial": 1, "identity_error": 1,
                      "universe_gap": 1, "missed_t2": 1}
    assert "model_related_miss" not in result
