"""EH-07 closing-day/T2 reliability guards.

Execution-only timing and status infrastructure. This module does not create
checkpoints, change V1.1 evidence rules, or decide scores/grades/recommendations.
It exists to make missed, early, unresolved and eligible closing-day states
explicit while preventing retrospective T2 creation.
"""
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Iterable
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
T2_NOT_BEFORE = time(19, 0)


@dataclass(frozen=True)
class ClosingIssue:
    canonical_id: str
    company_name: str
    issue_close_date: date


@dataclass(frozen=True)
class T2Status:
    canonical_id: str
    company_name: str
    issue_close_date: date
    code: str
    can_create_t2: bool
    reason: str


def _local_now(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(IST)


def evaluate_t2_status(
    issue: ClosingIssue,
    *,
    now: datetime,
    final_fields_verified: bool,
) -> T2Status:
    local_now = _local_now(now)
    today = local_now.date()

    if today < issue.issue_close_date:
        return T2Status(
            issue.canonical_id,
            issue.company_name,
            issue.issue_close_date,
            "NOT_CLOSING_TODAY",
            False,
            "issue closing date is in the future",
        )
    if today > issue.issue_close_date:
        return T2Status(
            issue.canonical_id,
            issue.company_name,
            issue.issue_close_date,
            "MISSED_T2_NO_BACKDATE",
            False,
            "closing day has passed; retrospective T2 is prohibited",
        )
    if local_now.time().replace(tzinfo=None) < T2_NOT_BEFORE:
        return T2Status(
            issue.canonical_id,
            issue.company_name,
            issue.issue_close_date,
            "TOO_EARLY",
            False,
            "final-day T2 is not eligible before 19:00 Asia/Kolkata",
        )
    if not final_fields_verified:
        return T2Status(
            issue.canonical_id,
            issue.company_name,
            issue.issue_close_date,
            "FINAL_EVIDENCE_UNRESOLVED",
            False,
            "closing-day final fields are not verified under existing V1.1 rules",
        )
    return T2Status(
        issue.canonical_id,
        issue.company_name,
        issue.issue_close_date,
        "T2_ELIGIBLE",
        True,
        "closing day, after 19:00 Asia/Kolkata, with verified final fields",
    )


def closing_day_plan(
    issues: Iterable[ClosingIssue],
    *,
    now: datetime,
    verified_final_ids: Iterable[str] = (),
) -> tuple[T2Status, ...]:
    """Return deterministic status for every reconciled issue relevant today/past.

    Future issues are retained with NOT_CLOSING_TODAY so orchestration can show
    why they were not finalized. Duplicated canonical IDs fail closed.
    """
    verified = set(verified_final_ids)
    seen: set[str] = set()
    statuses: list[T2Status] = []
    for issue in issues:
        if not issue.canonical_id:
            raise ValueError("canonical_id is required")
        if issue.canonical_id in seen:
            raise ValueError(f"duplicate canonical_id: {issue.canonical_id}")
        seen.add(issue.canonical_id)
        statuses.append(
            evaluate_t2_status(
                issue,
                now=now,
                final_fields_verified=issue.canonical_id in verified,
            )
        )
    return tuple(sorted(statuses, key=lambda status: (status.issue_close_date, status.canonical_id)))


def unresolved_or_missed(statuses: Iterable[T2Status]) -> tuple[T2Status, ...]:
    """Expose explicit operational alerts; never manufacture a checkpoint."""
    alert_codes = {"MISSED_T2_NO_BACKDATE", "FINAL_EVIDENCE_UNRESOLVED"}
    return tuple(status for status in statuses if status.code in alert_codes)
