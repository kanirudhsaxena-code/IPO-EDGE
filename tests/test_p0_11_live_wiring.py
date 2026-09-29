"""P0-11 acceptance guard: live T2 issuance must freeze its governed presentation.

This is intentionally a source-level release guard in addition to integration tests: it
prevents a future refactor from shipping a T2 writer that forgets the presentation
snapshot call. Transactional rollback is proved separately against disposable Postgres.
"""
from pathlib import Path


def test_live_runtime_wires_presentation_before_checkpoint_count():
    source = Path("src/ipo_edge/live_runtime.py").read_text()
    assert "from .presentation_snapshot import persist_live_snapshot" in source
    call = "persist_live_snapshot("
    assert call in source

    evidence_write = source.index("INSERT INTO research_evidence")
    presentation_write = source.index(call)
    checkpoint_count = source.index("checkpoint_count += 1")
    assert evidence_write < presentation_write < checkpoint_count
