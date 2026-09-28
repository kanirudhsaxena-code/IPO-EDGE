import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "execution_hardening_t2.py"
spec = importlib.util.spec_from_file_location("execution_hardening_t2", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

ClosingIssue = module.ClosingIssue
evaluate_t2_status = module.evaluate_t2_status
closing_day_plan = module.closing_day_plan
unresolved_or_missed = module.unresolved_or_missed


def issue(close_date=date(2026, 9, 28), canonical_id="IPO1"):
    return ClosingIssue(canonical_id, "Example IPO", close_date)


def test_closing_day_before_1900_ist_is_not_eligible():
    now = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)  # 17:30 IST
    status = evaluate_t2_status(issue(), now=now, final_fields_verified=True)
    assert status.code == "TOO_EARLY"
    assert not status.can_create_t2


def test_closing_day_after_1900_ist_with_verified_finals_is_eligible():
    now = datetime(2026, 9, 28, 14, 0, tzinfo=timezone.utc)  # 19:30 IST
    status = evaluate_t2_status(issue(), now=now, final_fields_verified=True)
    assert status.code == "T2_ELIGIBLE"
    assert status.can_create_t2


def test_unverified_final_fields_remain_explicitly_unresolved():
    now = datetime(2026, 9, 28, 14, 0, tzinfo=timezone.utc)
    status = evaluate_t2_status(issue(), now=now, final_fields_verified=False)
    assert status.code == "FINAL_EVIDENCE_UNRESOLVED"
    assert not status.can_create_t2


def test_past_closing_day_never_allows_retrospective_t2():
    now = datetime(2026, 9, 29, 14, 0, tzinfo=timezone.utc)
    status = evaluate_t2_status(issue(), now=now, final_fields_verified=True)
    assert status.code == "MISSED_T2_NO_BACKDATE"
    assert not status.can_create_t2
    assert "retrospective" in status.reason


def test_future_issue_is_not_closing_today():
    now = datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc)
    status = evaluate_t2_status(issue(), now=now, final_fields_verified=True)
    assert status.code == "NOT_CLOSING_TODAY"
    assert not status.can_create_t2


def test_naive_datetime_fails_closed():
    try:
        evaluate_t2_status(issue(), now=datetime(2026, 9, 28, 20, 0), final_fields_verified=True)
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("naive time must fail closed")


def test_duplicate_canonical_identity_fails_closed_in_closing_day_plan():
    now = datetime(2026, 9, 28, 14, 0, tzinfo=timezone.utc)
    duplicate = [issue(canonical_id="IPO1"), issue(canonical_id="IPO1")]
    try:
        closing_day_plan(duplicate, now=now, verified_final_ids={"IPO1"})
    except ValueError as exc:
        assert "duplicate canonical_id" in str(exc)
    else:
        raise AssertionError("duplicate canonical IDs must fail closed")


def test_every_missed_or_unresolved_t2_has_explicit_alert_reason():
    now = datetime(2026, 9, 29, 14, 0, tzinfo=timezone.utc)
    statuses = closing_day_plan(
        [issue(date(2026, 9, 28), "PAST"), issue(date(2026, 9, 29), "TODAY")],
        now=now,
        verified_final_ids=set(),
    )
    alerts = unresolved_or_missed(statuses)
    assert {status.code for status in alerts} == {"MISSED_T2_NO_BACKDATE", "FINAL_EVIDENCE_UNRESOLVED"}
    assert all(status.reason for status in alerts)
