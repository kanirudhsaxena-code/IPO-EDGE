"""Execution-hardening guardrails for frozen IPO EDGE history.

These tests intentionally protect the historical checkpoint contract rather than
replaying or rewriting history.  The database-level mutation test remains in
``tests/checkpoint_immutability.sql`` and is run only against an isolated test DB.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FROZEN_V10_COUNT = "123"
FROZEN_V10_FINGERPRINT = "5df3c7fc2ce6e3556a523ddfa03d32fb"


def test_frozen_v10_fixture_identity_is_pinned():
    sql = (ROOT / "tests" / "checkpoint_immutability.sql").read_text()
    assert f"<> {FROZEN_V10_COUNT}" in sql
    assert FROZEN_V10_FINGERPRINT in sql


def test_checkpoint_table_is_append_only_for_all_framework_versions():
    migration = (ROOT / "db" / "migrations" / "003_checkpoint_immutability.sql").read_text()
    assert "BEFORE UPDATE OR DELETE OR TRUNCATE ON public.checkpoints" in migration
    assert "ENABLE ALWAYS TRIGGER checkpoints_reject_mutation" in migration
    assert "GRANT SELECT, INSERT ON public.checkpoints TO ipo_edge_runtime" in migration
    assert "GRANT UPDATE ON public.checkpoints TO ipo_edge_runtime" not in migration
    assert "GRANT DELETE ON public.checkpoints TO ipo_edge_runtime" not in migration


def test_immutability_smoke_exercises_owner_and_runtime_mutations():
    sql = (ROOT / "tests" / "checkpoint_immutability.sql").read_text()
    for statement in (
        "UPDATE public.checkpoints SET decision=decision",
        "DELETE FROM public.checkpoints",
        "TRUNCATE public.checkpoints CASCADE",
    ):
        # Each command must be exercised once as owner and once as runtime role.
        assert sql.count(statement) == 2
    assert "SET LOCAL ROLE ipo_edge_runtime" in sql
    assert sql.rstrip().endswith("ROLLBACK;")
