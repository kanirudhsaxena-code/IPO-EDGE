from pathlib import Path

import pytest

from ipo_edge.presentation_snapshot import (
    assert_presentation_snapshot,
    build_presentation_snapshot,
    semantic_presentation_hash,
)


def test_cross_language_semantic_hash_vector_matches_console():
    basis = {
        "presentation_contract_version": "P0_11_PRESENTATION_V1",
        "engine": "5DR",
        "identity": {"run_id": "42", "result_id": "forecast-7", "checkpoint_id": None},
        "governance_state": "SELECTED",
        "sections": [
            {"name": "TABLE_1_5DR_ASSESSMENT_EFFICACY", "value": 1.0, "probability": 42.5, "verified": True},
            {"name": "TABLE_2_CURRENT_5DR_RUN", "items": ["PVPO", None, -0.0]},
        ],
        "source_payload_hash": "source-abc",
    }
    assert semantic_presentation_hash(basis) == "c7ab9fc4e43a3d10460f99b1e8bada4147e85f4878880ddd12c08bf66c4b0127"


def test_ipo_snapshot_requires_four_master_tables_and_exact_t2_identity():
    sections = [
        {"name": "EFFICACY_ASSESSMENT", "rows": []},
        {"name": "MISSED_OPPORTUNITIES", "rows": []},
        {"name": "CONTINUOUS_LEARNINGS", "rows": []},
        {"name": "CURRENT_OPPORTUNITIES", "rows": []},
    ]
    snapshot = build_presentation_snapshot(
        run_id=12,
        ipo_id=31,
        checkpoint_id=44,
        governance_state="SELECTED",
        source_payload_hash="source-ipo",
        sections=sections,
    )
    assert snapshot["engine"] == "IPO_EDGE"
    assert snapshot["identity"] == {"run_id": "12", "result_id": "31", "checkpoint_id": "44"}
    assert_presentation_snapshot(snapshot)

    with pytest.raises(ValueError, match="PRESENTATION_IPO_SECTION_ORDER_MISMATCH"):
        build_presentation_snapshot(
            run_id=12,
            ipo_id=31,
            checkpoint_id=44,
            governance_state="SELECTED",
            source_payload_hash="source-ipo",
            sections=list(reversed(sections)),
        )


def test_tamper_fails_closed():
    snapshot = build_presentation_snapshot(
        run_id=12,
        ipo_id=31,
        checkpoint_id=44,
        governance_state="SELECTED",
        source_payload_hash="source-ipo",
        sections=[
            {"name": "EFFICACY_ASSESSMENT"},
            {"name": "MISSED_OPPORTUNITIES"},
            {"name": "CONTINUOUS_LEARNINGS"},
            {"name": "CURRENT_OPPORTUNITIES"},
        ],
    )
    snapshot["identity"]["checkpoint_id"] = "45"
    with pytest.raises(ValueError, match="PRESENTATION_HASH_MISMATCH"):
        assert_presentation_snapshot(snapshot)


def test_migration_binds_run_ipo_and_t2_checkpoint_and_is_append_only():
    sql = Path("db/migrations/010_p0_11_presentation_snapshots.sql").read_text(encoding="utf-8")
    assert "run_id bigint NOT NULL REFERENCES public.run_log(run_id)" in sql
    assert "ipo_id bigint NOT NULL REFERENCES public.ipos(ipo_id)" in sql
    assert "checkpoint_id bigint NOT NULL REFERENCES public.checkpoints(checkpoint_id)" in sql
    assert "CHECK (result_id = ipo_id::text)" in sql
    assert "checkpoint_kind <> 'T2_FINAL_DAY'" in sql
    assert "checkpoint_ipo <> NEW.ipo_id" in sql
    assert "jsonb_array_length(sections)=4" in sql
    assert "presentation_snapshots_reject_mutation" in sql
    assert "INSERT INTO public.presentation_snapshots" not in sql


def test_rollback_refuses_to_delete_immutable_history():
    sql = Path("db/rollback/010_p0_11_presentation_snapshots.sql").read_text(encoding="utf-8")
    assert "immutable presentation snapshots already exist" in sql
    assert "EXISTS (SELECT 1 FROM public.presentation_snapshots LIMIT 1)" in sql
