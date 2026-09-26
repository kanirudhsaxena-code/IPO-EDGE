import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "execution_hardening_universe_providers.py"
spec = importlib.util.spec_from_file_location("execution_hardening_universe_providers", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
normalize_records = module.normalize_records
source_union = module.source_union


def test_identity_precedence_is_deterministic():
    batch = normalize_records("NSE", "MAINBOARD", [{"isin": "INE123", "name": "Example Ltd"}], enumerated=True, parse_ok=True)
    assert batch.parse_ok
    assert batch.records[0].identity == "INE123"


def test_malformed_record_fails_closed():
    batch = normalize_records("BSE", "SME", [{"name": ""}], enumerated=True, parse_ok=True)
    assert not batch.parse_ok
    assert "missing stable identity" in batch.error


def test_provider_failure_is_not_treated_as_healthy():
    batch = normalize_records("SEBI", "MAINBOARD", [], enumerated=False, parse_ok=False)
    assert not batch.parse_ok
    assert batch.records == ()


def test_upstox_is_opt_in_and_not_required_for_union():
    official = normalize_records("NSE", "MAINBOARD", [{"isin": "INE1"}], enumerated=True, parse_ok=True)
    upstox = normalize_records("UPSTOX", "MAINBOARD", [{"ipo_id": "UP1"}], enumerated=True, parse_ok=True)
    disabled = source_union([official, upstox], upstox_enabled=False)
    enabled = source_union([official, upstox], upstox_enabled=True)
    assert [r.identity for r in disabled["MAINBOARD"]] == ["INE1"]
    assert {r.identity for r in enabled["MAINBOARD"]} == {"INE1", "UP1"}


def test_mainboard_and_sme_union_remain_separate():
    main = normalize_records("SPECIALIST", "MAINBOARD", [{"name": "Main Ltd"}], enumerated=True, parse_ok=True)
    sme = normalize_records("SPECIALIST", "SME", [{"name": "Small Ltd"}], enumerated=True, parse_ok=True)
    result = source_union([main, sme])
    assert [r.identity for r in result["MAINBOARD"]] == ["Main Ltd"]
    assert [r.identity for r in result["SME"]] == ["Small Ltd"]
