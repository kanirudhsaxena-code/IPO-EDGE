from datetime import datetime, timezone
import hashlib
import pytest

from ipo_edge.evidence_contract import (
    EVIDENCE_STATES,
    IPO_VARIABLES,
    SOURCE_AUTHORITY,
    build_edge_ipo_export,
    normalize_evidence_item,
    source_health_from_attempt,
    verified_registrar_source,
    verify_edge_ipo_export,
)

NOW=datetime(2026,9,18,7,15,tzinfo=timezone.utc)
SUBJECT={"id":"fixture-mainboard-202609","name":"Fixture Limited","segment":"MAINBOARD"}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def item(variable,status="COMPLETE"):
    return normalize_evidence_item(
        variable_id=variable,
        status=status,
        values={"fixture":variable},
        sources=[{
            "name":"SEBI",
            "url":"https://www.sebi.gov.in/fixture",
            "source_type":"OFFICIAL_REGULATORY",
            "authority":1,
            "source_sha256":digest(variable),
            "published_at":NOW.isoformat(),
            "retrieved_at":NOW.isoformat(),
        }],
        observed_at=NOW,
    )


def test_evidence_states_match_governed_acquisition_semantics():
    assert EVIDENCE_STATES=={
        "COMPLETE","VERIFIED_PARTIAL","CONFLICTED","UNAVAILABLE","RECOVERED_VIA_FALLBACK"
    }


def test_verified_registrar_requires_sebi_registration_and_registry_provenance():
    row=verified_registrar_source(
        name="KFin Technologies Limited",
        url="https://www.kfintech.com/",
        sebi_registration_no="INR000000221",
        registry_url="https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=10&regNo=INR000000221",
        verified_at=NOW,
    )
    assert row["source_type"]=="REGISTRAR"
    assert row["authority"]==SOURCE_AUTHORITY["REGISTRAR"]
    with pytest.raises(ValueError):
        verified_registrar_source(
            name="bad",url="https://example.com",sebi_registration_no="BAD",
            registry_url="https://www.sebi.gov.in",verified_at=NOW,
        )


def test_existing_source_attempt_normalizes_to_required_health_fields():
    attempt={
        "source_name":"NSE public issues",
        "source_url":"https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
        "source_type":"EXCHANGE",
        "authority":2,
        "retrieved_at":NOW.isoformat(),
        "success":False,
        "error":"RATE_LIMITED",
        "recovery_attempt":2,
        "fallback_source_used":"https://ipomarkets.com/ipo-calendar/september-2026",
        "final_source_status":"SOURCE_FAILED",
    }
    health=source_health_from_attempt(attempt)
    assert set(health)=={
        "name","url","source_type","authority","timestamp","success","error",
        "recovery_attempt","fallback","final_status"
    }


def test_complete_shared_export_is_facts_only_and_ready():
    evidence=[item(v) for v in IPO_VARIABLES]
    bundle=build_edge_ipo_export(
        subject=SUBJECT,run_id="IPO-EDGE-1",frozen_at=NOW,evidence=evidence,
    )
    assert bundle["status"]=="READY"
    assert bundle["coverage"]["missing_variables"]==[]
    assert bundle["methodology_applied"] is False
    assert bundle["scoring_applied"] is False
    assert bundle["grade_assigned"] is False
    assert bundle["recommendation_generated"] is False
    assert verify_edge_ipo_export(bundle)["status"]=="READY"


def test_missing_or_conflicted_variable_blocks_export():
    bundle=build_edge_ipo_export(
        subject=SUBJECT,run_id="IPO-EDGE-2",frozen_at=NOW,
        evidence=[item(v) for v in IPO_VARIABLES[:-1]],
    )
    assert bundle["status"]=="BLOCKED"
    assert bundle["coverage"]["missing_variables"]==["IPO_ENVIRONMENT"]

    evidence=[item(v) for v in IPO_VARIABLES]
    evidence[-1]=item("IPO_ENVIRONMENT","CONFLICTED")
    bundle=build_edge_ipo_export(
        subject=SUBJECT,run_id="IPO-EDGE-3",frozen_at=NOW,evidence=evidence,
    )
    assert bundle["status"]=="BLOCKED"
    assert bundle["coverage"]["unresolved_variables"]==["IPO_ENVIRONMENT"]


def test_export_tampering_detected():
    bundle=build_edge_ipo_export(
        subject=SUBJECT,run_id="IPO-EDGE-4",frozen_at=NOW,
        evidence=[item(v) for v in IPO_VARIABLES],
    )
    bundle["subject"]["name"]="Tampered"
    with pytest.raises(ValueError,match="fingerprint"):
        verify_edge_ipo_export(bundle)
