from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from .evidence import filter_for_checkpoint
from .research import derive_component_scores, research_gate
from .scoring import calculate_score


def build_checkpoint(items, checkpoint_time: datetime, checkpoint_type: str, *, framework_version="1.0"):
    allowed = filter_for_checkpoint(list(items), checkpoint_time)
    gate_ok, blocker = research_gate(allowed)
    component_scores = derive_component_scores(allowed)
    result = calculate_score(
        component_scores,
        critical_evidence_verified=gate_ok,
        hard_blocker=blocker,
    )
    return {
        "checkpoint_type": checkpoint_type,
        "checkpoint_time": checkpoint_time,
        "score": result.score,
        "grade": result.grade,
        "decision": result.decision,
        "bear_gain_estimate": None,
        "base_gain_estimate": None,
        "bull_gain_estimate": None,
        "confidence": None,
        "hard_blocker": result.hard_blocker,
        "evidence_delta_summary": {
            "evidence_count": len(allowed),
            "component_scores": component_scores,
        },
        "framework_version": framework_version,
    }


def classify_outcome(final_grade: str, actual_gain: float) -> str:
    recommended = final_grade in {"A+", "A++"}
    if recommended and actual_gain >= 20:
        return "STRONG_HIT"
    if recommended and actual_gain >= 0:
        return "MODERATE_HIT"
    if recommended:
        return "FALSE_POSITIVE"
    if actual_gain >= 20:
        return "MISSED_OPPORTUNITY"
    return "CORRECT_AVOIDANCE"
