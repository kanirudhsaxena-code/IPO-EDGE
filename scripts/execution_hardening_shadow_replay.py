"""Execution-hardening historical shadow replay helpers.

This module is deliberately model-agnostic.  It never rescales, regrades, or
redecides a frozen checkpoint.  It only validates temporal eligibility,
compares canonical and shadow outputs for identical evidence, and aggregates
execution-layer diagnostics.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping, Sequence

MODEL_RELATED_DEFERRED = "MODEL_RELATED_DEFERRED"


@dataclass(frozen=True)
class FrozenCase:
    case_id: str
    checkpoint_at: datetime
    evidence_as_of: datetime
    evidence_fingerprint: str
    score: object
    grade: object
    decision: object
    outcome_fingerprint: str


@dataclass(frozen=True)
class ShadowResult:
    case_id: str
    evidence_as_of: datetime
    evidence_fingerprint: str
    score: object
    grade: object
    decision: object
    canonical_outcome_fingerprint: str
    retrieval_nv: bool = False
    partial: bool = False
    identity_error: bool = False
    universe_gap: bool = False
    missed_t2: bool = False
    model_related_miss: bool = False


def validate_no_future_evidence(case: FrozenCase, shadow: ShadowResult) -> None:
    """Fail closed if replay could see evidence unavailable at the checkpoint."""
    if case.evidence_as_of > case.checkpoint_at:
        raise ValueError("frozen case contains future evidence")
    if shadow.evidence_as_of > case.checkpoint_at:
        raise ValueError("shadow replay attempted future-data leakage")


def assert_same_evidence_same_model_output(case: FrozenCase, shadow: ShadowResult) -> None:
    """Enforce the model lock whenever evidence fingerprints are identical."""
    validate_no_future_evidence(case, shadow)
    if case.evidence_fingerprint != shadow.evidence_fingerprint:
        return
    canonical = (case.score, case.grade, case.decision)
    replayed = (shadow.score, shadow.grade, shadow.decision)
    if canonical != replayed:
        raise AssertionError("model-rule drift: identical evidence changed model output")


def assert_history_immutable(case: FrozenCase, shadow: ShadowResult) -> None:
    """Shadow execution may reference but never replace a canonical outcome."""
    if shadow.canonical_outcome_fingerprint != case.outcome_fingerprint:
        raise AssertionError("frozen historical outcome mutation detected")


def replay_guard(case: FrozenCase, shadow: ShadowResult) -> None:
    if case.case_id != shadow.case_id:
        raise ValueError("shadow result does not match frozen case")
    validate_no_future_evidence(case, shadow)
    assert_history_immutable(case, shadow)
    assert_same_evidence_same_model_output(case, shadow)


def classify_miss(shadow: ShadowResult) -> str | None:
    """Model-related misses are diagnostic only and can never be 'fixed' here."""
    return MODEL_RELATED_DEFERRED if shadow.model_related_miss else None


def measure_execution_deltas(
    before: Sequence[Mapping[str, bool]], after: Sequence[Mapping[str, bool]]
) -> dict[str, int]:
    """Return before-minus-after counts for execution defects only."""
    keys = ("retrieval_nv", "partial", "identity_error", "universe_gap", "missed_t2")
    return {
        key: sum(bool(row.get(key)) for row in before)
        - sum(bool(row.get(key)) for row in after)
        for key in keys
    }


def validate_replay_batch(pairs: Iterable[tuple[FrozenCase, ShadowResult]]) -> dict[str, int]:
    checked = deferred = 0
    for case, shadow in pairs:
        replay_guard(case, shadow)
        checked += 1
        deferred += int(classify_miss(shadow) == MODEL_RELATED_DEFERRED)
    return {"checked": checked, "model_related_deferred": deferred}
