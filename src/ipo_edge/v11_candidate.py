from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class V11OverlayResult:
    lane_triggered: bool
    actionable_candidate: bool
    reason: str


def institutional_demand_lane(
    component_scores: Mapping[str, float | None],
    *,
    critical_evidence_verified: bool,
    hard_blocker: str | None = None,
) -> V11OverlayResult:
    """Validated V1.1 candidate overlay.

    This does not change the frozen V1.0 score or historical grade. It identifies
    a separately validated institutional+demand candidate only when the existing
    critical-evidence and blocker safeguards are satisfied.
    """
    if hard_blocker:
        return V11OverlayResult(False, False, f"HARD_BLOCKER:{hard_blocker}")
    if not critical_evidence_verified:
        return V11OverlayResult(False, False, "CRITICAL_EVIDENCE_NOT_VERIFIED")

    r6 = component_scores.get("institutional_conviction")
    r7 = component_scores.get("market_demand")
    if r6 is None or r7 is None:
        return V11OverlayResult(False, False, "R6_R7_NOT_VERIFIED")

    triggered = float(r6) >= 0.85 and float(r7) >= 0.80
    return V11OverlayResult(
        triggered,
        triggered,
        "VALIDATED_R6_R7_LANE" if triggered else "LANE_NOT_MET",
    )
