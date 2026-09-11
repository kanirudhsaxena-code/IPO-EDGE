from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .efficacy import OutcomeRecord, summarize
from .scoring import calculate_score


@dataclass(frozen=True)
class BacktestCase:
    company_name: str
    checkpoint_time: datetime
    component_scores: dict[str, float | None]
    critical_evidence_verified: bool
    actual_listing_gain: float
    estimated_base_gain: float | None = None
    hard_blocker: str | None = None
    upgraded_on_final_day: bool = False


def evaluate_case(case: BacktestCase) -> dict:
    score = calculate_score(
        case.component_scores,
        critical_evidence_verified=case.critical_evidence_verified,
        hard_blocker=case.hard_blocker,
    )
    missed = score.grade not in {"A+", "A++"} and case.actual_listing_gain >= 20
    return {
        "company_name": case.company_name,
        "checkpoint_time": case.checkpoint_time,
        "score": score.score,
        "grade": score.grade,
        "decision": score.decision,
        "hard_blocker": score.hard_blocker,
        "actual_listing_gain": case.actual_listing_gain,
        "estimated_base_gain": case.estimated_base_gain,
        "missed_opportunity": missed,
        "upgraded_on_final_day": case.upgraded_on_final_day,
    }


def summarize_backtest(cases: Iterable[BacktestCase]):
    evaluated = [evaluate_case(c) for c in cases]
    metrics = summarize(
        OutcomeRecord(
            grade=row["grade"],
            actual_gain=row["actual_listing_gain"],
            estimated_gain=row["estimated_base_gain"],
            upgraded_on_final_day=row["upgraded_on_final_day"],
        )
        for row in evaluated
    )
    return evaluated, metrics
