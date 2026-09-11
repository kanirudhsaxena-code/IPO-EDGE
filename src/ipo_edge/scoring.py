from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

WEIGHTS = {
    "business_quality": 15,
    "financial_quality": 15,
    "valuation": 20,
    "institutional_conviction": 20,
    "market_demand": 10,
    "analyst_consensus": 10,
    "sector_ipo_environment": 5,
    "gmp_confirmation": 5,
}


@dataclass(frozen=True)
class ScoreResult:
    score: float | None
    grade: str
    decision: str
    hard_blocker: str | None


def grade_from_score(score: float) -> tuple[str, str]:
    if score >= 95:
        return "A++", "STRONG_SUBSCRIBE"
    if score >= 90:
        return "A+", "SUBSCRIBE"
    if score >= 85:
        return "A", "TRACK"
    return "REJECT", "REJECT"


def calculate_score(
    component_scores: Mapping[str, float | None],
    *,
    critical_evidence_verified: bool,
    hard_blocker: str | None = None,
) -> ScoreResult:
    """Score one IPO using frozen V1.0 weights.

    Component values are normalized 0..1 evidence-quality scores. Missing critical
    evidence or a hard blocker prevents A+/A++ irrespective of arithmetic score.
    """
    if hard_blocker:
        return ScoreResult(None, "NV", "NO_ACTION", hard_blocker)
    if not critical_evidence_verified:
        return ScoreResult(None, "NV", "NO_ACTION", "CRITICAL_EVIDENCE_NOT_VERIFIED")

    missing = [key for key in WEIGHTS if component_scores.get(key) is None]
    if missing:
        return ScoreResult(None, "NV", "NO_ACTION", f"MISSING_COMPONENTS:{','.join(missing)}")

    total = 0.0
    for key, weight in WEIGHTS.items():
        value = float(component_scores[key])
        if not 0 <= value <= 1:
            raise ValueError(f"{key} must be in [0,1], got {value}")
        total += value * weight

    score = round(total, 2)
    grade, decision = grade_from_score(score)
    return ScoreResult(score, grade, decision, None)
