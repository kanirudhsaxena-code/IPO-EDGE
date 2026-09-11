import json
import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / "config" / "framework_v1.1.json").read_text())
scoring = json.loads((ROOT / "config" / "scoring_v1.0.json").read_text())
base_rules = json.loads((ROOT / "config" / "rules_v1.0.json").read_text())

rules = {
    **base_rules,
    "base_version": config["base_version"],
    "institutional_demand_lane": config["validated_overlay"],
    "evidence_recovery": config["evidence_recovery"],
    "rejected_changes": config["rejected_changes"],
    "production_activation_approved": True,
}

spec_url = "https://docs.google.com/document/d/17Znmj-rASDDuPbb9aRD9M6nZYlnDVVZfl7Qgg--eZjo/edit"

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO framework_versions
                (version, status, effective_at, scoring_config, rules_config, source_spec_document_url)
            VALUES
                (%s, 'FROZEN', %s::timestamptz, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (version) DO NOTHING
            """,
            (
                config["version"],
                "2026-09-11T13:40:00Z",
                json.dumps(scoring),
                json.dumps(rules),
                spec_url,
            ),
        )
        cur.execute(
            "SELECT version, status, effective_at, source_spec_document_url, rules_config FROM framework_versions WHERE version = '1.1'"
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError("V1.1 registration failed")
        version, status, effective_at, source_url, stored_rules = row
        if status != "FROZEN":
            raise RuntimeError(f"Unexpected V1.1 status: {status}")
        if source_url != spec_url:
            raise RuntimeError("V1.1 source specification URL mismatch")
        if "institutional_demand_lane" not in stored_rules or "evidence_recovery" not in stored_rules:
            raise RuntimeError("V1.1 rules missing validated overlay or evidence recovery")
        print(json.dumps({
            "version": version,
            "status": status,
            "effective_at": effective_at.isoformat(),
            "source_spec_document_url": source_url,
            "institutional_demand_lane": stored_rules["institutional_demand_lane"],
            "evidence_recovery": stored_rules["evidence_recovery"],
        }, indent=2, default=str))
