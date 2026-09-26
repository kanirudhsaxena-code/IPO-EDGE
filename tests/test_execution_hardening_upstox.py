import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "execution_hardening_upstox.py"
spec = importlib.util.spec_from_file_location("execution_hardening_upstox", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
fetch = module.fetch_upstox_read_only
critical_evidence_satisfied = module.critical_evidence_satisfied


def test_feature_flag_fails_closed_without_transport_call():
    called = []
    result = fetch("ipo_discovery", {}, enabled=False, credential_present=True,
                   transport=lambda op, req: called.append((op, req)))
    assert not result.available
    assert called == []
    assert "UPSTOX_ENABLED" in result.error


def test_missing_credential_is_explicit_and_nonfatal():
    result = fetch("ipo_details", {"id": "UP1"}, enabled=True,
                   credential_present=False, transport=lambda op, req: {})
    assert not result.available
    assert result.error == "missing Upstox read-only credential"


def test_non_read_only_operation_is_rejected():
    result = fetch("place_order", {}, enabled=True, credential_present=True,
                   transport=lambda op, req: {"unexpected": True})
    assert not result.available
    assert "not allow-listed" in result.error


def test_provider_outage_does_not_raise_or_stop_fallback():
    def outage(op, req):
        raise TimeoutError("provider timeout")
    result = fetch("market_information", {}, enabled=True,
                   credential_present=True, transport=outage)
    assert not result.available
    assert result.error == "Upstox unavailable: TimeoutError"


def test_read_only_success_returns_structured_data():
    result = fetch("fundamentals", {"symbol": "EXAMPLE"}, enabled=True,
                   credential_present=True, transport=lambda op, req: {"ok": True})
    assert result.available
    assert result.data == {"ok": True}


def test_upstox_never_satisfies_critical_evidence_alone():
    assert not critical_evidence_satisfied(upstox_available=True, independent_verified_sources=0)
    assert critical_evidence_satisfied(upstox_available=False, independent_verified_sources=1)
