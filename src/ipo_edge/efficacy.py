from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Iterable


@dataclass(frozen=True)
class OutcomeRecord:
    grade: str
    actual_gain: float
    estimated_gain: float | None = None
    upgraded_on_final_day: bool = False


@dataclass(frozen=True)
class EfficacySummary:
    recommendation_count: int
    positive_hit_rate: float | None
    twenty_percent_hit_rate: float | None
    a_plus_plus_hit_rate: float | None
    a_plus_hit_rate: float | None
    opportunity_capture_rate: float | None
    miss_rate: float | None
    false_positive_rate: float | None
    correct_avoidance_rate: float | None
    avg_recommended_gain: float | None
    avg_estimated_gain: float | None
    forecast_error: float | None
    upgrade_hit_rate: float | None


def _rate(n: int, d: int) -> float | None:
    return None if d == 0 else round(n / d, 4)


def summarize(records: Iterable[OutcomeRecord]) -> EfficacySummary:
    rows = list(records)
    recs = [r for r in rows if r.grade in {"A+", "A++"}]
    avoids = [r for r in rows if r.grade not in {"A+", "A++"}]
    winners20 = [r for r in rows if r.actual_gain >= 20]
    misses = [r for r in avoids if r.actual_gain >= 20]
    false_pos = [r for r in recs if r.actual_gain < 0]
    correct_avoids = [r for r in avoids if r.actual_gain < 20]
    app = [r for r in recs if r.grade == "A++"]
    ap = [r for r in recs if r.grade == "A+"]
    upgraded = [r for r in recs if r.upgraded_on_final_day]
    with_est = [r for r in recs if r.estimated_gain is not None]

    return EfficacySummary(
        recommendation_count=len(recs),
        positive_hit_rate=_rate(sum(r.actual_gain >= 0 for r in recs), len(recs)),
        twenty_percent_hit_rate=_rate(sum(r.actual_gain >= 20 for r in recs), len(recs)),
        a_plus_plus_hit_rate=_rate(sum(r.actual_gain >= 20 for r in app), len(app)),
        a_plus_hit_rate=_rate(sum(r.actual_gain >= 20 for r in ap), len(ap)),
        opportunity_capture_rate=_rate(sum(r.grade in {"A+", "A++"} for r in winners20), len(winners20)),
        miss_rate=_rate(len(misses), len(winners20)),
        false_positive_rate=_rate(len(false_pos), len(recs)),
        correct_avoidance_rate=_rate(len(correct_avoids), len(avoids)),
        avg_recommended_gain=None if not recs else round(mean(r.actual_gain for r in recs), 2),
        avg_estimated_gain=None if not with_est else round(mean(float(r.estimated_gain) for r in with_est), 2),
        forecast_error=None if not with_est else round(mean(abs(r.actual_gain - float(r.estimated_gain)) for r in with_est), 2),
        upgrade_hit_rate=_rate(sum(r.actual_gain >= 20 for r in upgraded), len(upgraded)),
    )
