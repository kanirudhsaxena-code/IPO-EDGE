import json
from pathlib import Path

def test_release_manifest_binds_ipo_v11_framework():
    manifest = json.loads(Path("governance/production_release_manifest.json").read_text(encoding="utf-8"))
    framework = json.loads(Path("config/framework_v1.1.json").read_text(encoding="utf-8"))
    assert manifest["consumer"] == "IPO_EDGE"
    assert manifest["binding_status"] == "BOUND"
    spec = manifest["master_spec"]
    binding = manifest["production_binding"]
    assert spec["canonical_spec_version"] == "IPO EDGE V1.1"
    assert len(spec["content_sha256_lf"]) == 64
    int(spec["content_sha256_lf"], 16)
    assert binding["framework_version"] == framework["version"] == "1.1"
    assert binding["framework_status"] == framework["status"] == "PRODUCTION"
    assert binding["base_score_weights_unchanged"] == framework["base_score_weights_unchanged"]
    assert binding["base_grade_thresholds_unchanged"] == framework["base_grade_thresholds_unchanged"]
    assert binding["critical_evidence_policy_unchanged"] == framework["critical_evidence_policy_unchanged"]
