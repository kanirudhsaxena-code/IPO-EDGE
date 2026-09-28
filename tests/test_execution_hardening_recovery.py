import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "execution_hardening_recovery.py"
spec = importlib.util.spec_from_file_location("execution_hardening_recovery", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

Attempt = module.RecoveryAttempt
build_state = module.build_state
next_source = module.next_source
preferred_sources = module.preferred_sources
recovery_audit = module.recovery_audit


def attempt(block, provider, group, *, fetch=False, parse=False, verified=False,
            status=None, blocked=None):
    return Attempt(
        block=block,
        provider=provider,
        provenance_group=group,
        independence_basis=f"independent basis for {group}",
        fetch_ok=fetch,
        parse_ok=parse,
        verified=verified,
        http_status=status,
        blocked_reason=blocked,
    )


def test_source_order_is_deterministic_for_every_r_block():
    for index in range(1, 9):
        sources = preferred_sources(f"R{index}")
        assert isinstance(sources, tuple)
        assert len(sources) >= 2


def test_two_attempts_from_same_provenance_do_not_satisfy_critical_recovery():
    attempts = [
        attempt("R4", "SEBI_RHP", "same_filing"),
        attempt("R4", "EXCHANGE_DISCLOSURE", "same_filing"),
    ]
    state = build_state("R4", attempts)
    assert len(state.independent_attempt_groups) == 1
    assert not state.recovery_requirement_satisfied


def test_two_independent_attempts_satisfy_unresolved_critical_recovery_precondition():
    attempts = [
        attempt("R7", "NSE_SUBSCRIPTION", "nse"),
        attempt("R7", "BSE_SUBSCRIPTION", "bse"),
    ]
    state = build_state("R7", attempts)
    assert len(state.independent_attempt_groups) == 2
    assert state.recovery_requirement_satisfied
    assert not state.verified_attempts


def test_verified_evidence_requires_fetch_and_parse_success():
    try:
        attempt("R2", "SEBI_RHP", "sebi", verified=True)
    except ValueError as exc:
        assert "verification requires" in str(exc)
    else:
        raise AssertionError("verified evidence must not bypass fetch/parse")


def test_parse_success_cannot_exist_without_fetch_success():
    try:
        attempt("R3", "SEBI_RHP", "sebi", parse=True)
    except ValueError as exc:
        assert "parse success requires" in str(exc)
    else:
        raise AssertionError("parse success must require fetch success")


def test_401_403_and_captcha_routes_are_classified_blocked_and_not_retried():
    first = attempt("R4", "SEBI_RHP", "sebi", status=403)
    second = attempt("R4", "EXCHANGE_DISCLOSURE", "exchange", blocked="CAPTCHA encountered")
    assert first.route_blocked
    assert second.route_blocked
    assert next_source("R4", [first, second]) == "INDEPENDENT_RESEARCH_1"


def test_next_source_never_attempts_bypass_of_failed_route():
    failed = attempt("R7", "NSE_SUBSCRIPTION", "nse", status=401)
    assert next_source("R7", [failed]) == "BSE_SUBSCRIPTION"


def test_fetch_parse_and_verification_are_exposed_separately_in_audit():
    attempts = [
        attempt("R2", "SEBI_RHP", "sebi", fetch=True, parse=False, verified=False),
        attempt("R2", "EXCHANGE_OFFER_DOC", "exchange", fetch=True, parse=True, verified=False),
    ]
    audit = recovery_audit("R2", attempts)
    assert audit["attempts"][0]["fetch_ok"] is True
    assert audit["attempts"][0]["parse_ok"] is False
    assert audit["attempts"][1]["parse_ok"] is True
    assert audit["attempts"][1]["verified"] is False
    assert audit["recovery_requirement_satisfied"] is True


def test_successful_verified_attempt_satisfies_recovery_without_changing_policy():
    attempts = [
        attempt("R6", "EXCHANGE_ANCHOR_NOTICE", "exchange", fetch=True, parse=True, verified=True),
    ]
    state = build_state("R6", attempts)
    assert state.recovery_requirement_satisfied
    assert len(state.verified_attempts) == 1
