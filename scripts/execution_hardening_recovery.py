"""EH-05 deterministic R1-R8 recovery ladder.

Execution-hardening infrastructure only. This module contains no scoring,
grade, threshold, NV-gate, recommendation or historical mutation logic.
It models source ordering, provenance independence, route blocking and the
separation of fetch/parse/verification outcomes so orchestration can prove
that critical recovery was genuinely exhausted before an unresolved block is
eligible to remain NV under the existing V1.1 rules.
"""
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

CRITICAL_BLOCKS = frozenset({"R2", "R3", "R4", "R6", "R7"})
MIN_INDEPENDENT_ATTEMPTS = 2

# Provider labels are execution routes, not assertions that every route is
# available for every IPO. Orchestration skips unavailable/blocked routes and
# records that fact explicitly.
SOURCE_ORDER: Mapping[str, tuple[str, ...]] = {
    "R1": ("SEBI_RHP", "EXCHANGE_OFFER_DOC", "ISSUER", "INDEPENDENT_SPECIALIST_1"),
    "R2": ("SEBI_RHP", "EXCHANGE_OFFER_DOC", "ISSUER", "INDEPENDENT_RESEARCH_1"),
    "R3": ("SEBI_RHP", "EXCHANGE_OFFER_DOC", "INDEPENDENT_SPECIALIST_1", "INDEPENDENT_RESEARCH_1"),
    "R4": ("SEBI_RHP", "EXCHANGE_DISCLOSURE", "INDEPENDENT_RESEARCH_1", "INDEPENDENT_MEDIA_1"),
    "R5": ("INDEPENDENT_RESEARCH_1", "INDEPENDENT_RESEARCH_2", "INDEPENDENT_MEDIA_1"),
    "R6": ("EXCHANGE_ANCHOR_NOTICE", "SEBI_RHP", "INDEPENDENT_SPECIALIST_1", "INDEPENDENT_RESEARCH_1"),
    "R7": ("NSE_SUBSCRIPTION", "BSE_SUBSCRIPTION", "INDEPENDENT_SPECIALIST_1", "INDEPENDENT_SPECIALIST_2", "UPSTOX_SUPPLEMENTAL"),
    "R8": ("EXCHANGE_MARKET_DATA", "INDEPENDENT_MARKET_DATA_1", "INDEPENDENT_RESEARCH_1"),
}

HARD_BLOCK_HTTP_STATUSES = frozenset({401, 403})


@dataclass(frozen=True)
class RecoveryAttempt:
    block: str
    provider: str
    provenance_group: str
    independence_basis: str
    fetch_ok: bool
    parse_ok: bool
    verified: bool
    http_status: int | None = None
    blocked_reason: str | None = None

    def __post_init__(self) -> None:
        if self.block not in SOURCE_ORDER:
            raise ValueError(f"unknown research block: {self.block}")
        if not self.provider:
            raise ValueError("provider is required")
        if not self.provenance_group:
            raise ValueError("provenance_group is required")
        if not self.independence_basis:
            raise ValueError("independence_basis is required")
        if self.parse_ok and not self.fetch_ok:
            raise ValueError("parse success requires fetch success")
        if self.verified and not (self.fetch_ok and self.parse_ok):
            raise ValueError("verification requires successful fetch and parse")

    @property
    def route_blocked(self) -> bool:
        if self.http_status in HARD_BLOCK_HTTP_STATUSES:
            return True
        reason = (self.blocked_reason or "").upper()
        return "CAPTCHA" in reason or "ACCESS BLOCKED" in reason


@dataclass(frozen=True)
class RecoveryState:
    block: str
    attempts: tuple[RecoveryAttempt, ...]

    @property
    def verified_attempts(self) -> tuple[RecoveryAttempt, ...]:
        return tuple(attempt for attempt in self.attempts if attempt.verified)

    @property
    def independent_attempt_groups(self) -> frozenset[str]:
        return frozenset(attempt.provenance_group for attempt in self.attempts)

    @property
    def recovery_requirement_satisfied(self) -> bool:
        """Whether an unresolved critical block has the required attempts.

        This does not decide NV. It only proves the execution-layer recovery
        precondition required before the existing model/policy may leave a
        critical block unresolved.
        """
        if self.block not in CRITICAL_BLOCKS:
            return True
        if self.verified_attempts:
            return True
        return len(self.independent_attempt_groups) >= MIN_INDEPENDENT_ATTEMPTS


def preferred_sources(block: str) -> tuple[str, ...]:
    if block not in SOURCE_ORDER:
        raise ValueError(f"unknown research block: {block}")
    return SOURCE_ORDER[block]


def next_source(block: str, attempts: Sequence[RecoveryAttempt]) -> str | None:
    """Return the next legitimate route in deterministic order.

    A route already attempted is never retried by this deterministic ladder.
    A 401/403/CAPTCHA/access-blocked route is therefore abandoned rather than
    bypassed; the caller moves to the next legitimate provider.
    """
    order = preferred_sources(block)
    attempted = {attempt.provider for attempt in attempts if attempt.block == block}
    for provider in order:
        if provider not in attempted:
            return provider
    return None


def build_state(block: str, attempts: Iterable[RecoveryAttempt]) -> RecoveryState:
    scoped = tuple(attempt for attempt in attempts if attempt.block == block)
    return RecoveryState(block=block, attempts=scoped)


def recovery_audit(block: str, attempts: Iterable[RecoveryAttempt]) -> dict[str, object]:
    """Return an auditable execution-only status payload."""
    state = build_state(block, attempts)
    return {
        "block": block,
        "critical": block in CRITICAL_BLOCKS,
        "attempt_count": len(state.attempts),
        "independent_attempt_count": len(state.independent_attempt_groups),
        "verified": bool(state.verified_attempts),
        "recovery_requirement_satisfied": state.recovery_requirement_satisfied,
        "next_source": next_source(block, state.attempts),
        "attempts": [
            {
                "provider": attempt.provider,
                "provenance_group": attempt.provenance_group,
                "independence_basis": attempt.independence_basis,
                "fetch_ok": attempt.fetch_ok,
                "parse_ok": attempt.parse_ok,
                "verified": attempt.verified,
                "http_status": attempt.http_status,
                "blocked_reason": attempt.blocked_reason,
                "route_blocked": attempt.route_blocked,
            }
            for attempt in state.attempts
        ],
    }
