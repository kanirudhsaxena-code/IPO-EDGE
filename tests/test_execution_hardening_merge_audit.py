import importlib.util
from pathlib import Path

P = Path(__file__).parents[1] / "scripts" / "execution_hardening_merge_audit.py"
spec = importlib.util.spec_from_file_location("execution_hardening_merge_audit", P)
mod = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_execution_only_hardening_passes():
    a = mod.classify([
        "scripts/execution_hardening_recovery.py",
        "tests/test_execution_hardening_recovery.py",
        "docs/EXECUTION_HARDENING_BUILD.md",
    ], "main", "HEAD")
    assert a.pass_fail_closed
    assert not a.suspicious
    assert not a.frozen_surface_touched


def test_framework_change_fails_closed():
    a = mod.classify(["config/framework_v1.1.json"], "main", "HEAD")
    assert not a.pass_fail_closed
    assert "config/framework_v1.1.json" in a.frozen_surface_touched


def test_unclassified_file_fails_closed():
    a = mod.classify(["app/model.py"], "main", "HEAD")
    assert not a.pass_fail_closed
    assert a.suspicious == ("app/model.py",)


def test_history_like_change_fails_closed_even_under_hardening_prefix():
    a = mod.classify(["scripts/execution_hardening_historical_outcome.py"], "main", "HEAD")
    assert not a.pass_fail_closed
    assert a.frozen_surface_touched
