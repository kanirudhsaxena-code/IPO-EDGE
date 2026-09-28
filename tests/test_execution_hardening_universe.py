import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "execution_hardening_universe.py"
spec = importlib.util.spec_from_file_location("execution_hardening_universe", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
Observation = module.Observation
SourceRun = module.SourceRun
reconcile_segment = module.reconcile_segment
reconcile_universe = module.reconcile_universe


def run(source, segment, ids=(), enumerated=True, parse_ok=True):
    return SourceRun(source, segment, enumerated, parse_ok,
                     tuple(Observation(source, segment, x) for x in ids))


def test_single_source_cannot_claim_complete():
    result = reconcile_segment("MAINBOARD", [run("NSE", "MAINBOARD", ["A"])] )
    assert result.status == "PARTIAL"


def test_outage_or_parse_failure_cannot_define_empty_universe():
    result = reconcile_segment("SME", [run("NSE", "SME", enumerated=False, parse_ok=False)])
    assert result.status == "FAILED"


def test_empty_requires_two_healthy_official_enumerations():
    assert reconcile_segment("SME", [run("NSE", "SME"), run("CALENDAR", "SME")]).status == "PARTIAL"
    assert reconcile_segment("SME", [run("NSE", "SME"), run("BSE", "SME")]).status == "COMPLETE"


def test_union_and_discrepancy_are_auditable():
    result = reconcile_segment("MAINBOARD", [
        run("NSE", "MAINBOARD", ["A", "B"]),
        run("BSE", "MAINBOARD", ["A"]),
    ])
    assert result.status == "COMPLETE"
    assert result.identities == frozenset({"A", "B"})
    assert result.discrepancies["BSE"] == ("B",)


def test_mainboard_and_sme_reconcile_independently():
    results = reconcile_universe([
        run("NSE", "MAINBOARD", ["M"]), run("BSE", "MAINBOARD", ["M"]),
        run("NSE", "SME", ["S"]),
    ])
    assert results["MAINBOARD"].status == "COMPLETE"
    assert results["SME"].status == "PARTIAL"
