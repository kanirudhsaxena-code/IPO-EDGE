import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "execution_hardening_v1.1.json"


def _config():
    return json.loads(CONFIG.read_text())


def test_hardening_is_shadow_only_and_off_by_default():
    cfg = _config()
    assert cfg["model_policy"] == "FROZEN"
    assert cfg["shadow_only"] is True
    assert cfg["production_writes"] is False
    assert cfg["rollback"]["master_enabled"] is False
    assert all(enabled is False for enabled in cfg["features"].values())


def test_non_negotiable_mutation_and_leakage_switches_are_closed():
    inv = _config()["invariants"]
    assert inv == {
        "allow_model_changes": False,
        "allow_historical_checkpoint_mutation": False,
        "allow_historical_outcome_mutation": False,
        "allow_retrospective_t2": False,
        "allow_future_evidence": False,
    }
