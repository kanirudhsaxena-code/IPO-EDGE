"""EH-04 fail-closed Upstox read-only provider boundary.

This module is execution infrastructure only. It cannot write to Upstox or IPO
EDGE storage and it contains no model/scoring/recommendation logic. Callers
supply a read-only transport so credentials remain outside the repository.
"""
from dataclasses import dataclass
from typing import Any, Callable, Mapping

READ_ONLY_OPERATIONS = frozenset({
    "ipo_discovery",
    "ipo_details",
    "market_information",
    "fundamentals",
    "news",
})


@dataclass(frozen=True)
class UpstoxResult:
    operation: str
    available: bool
    data: Any = None
    error: str | None = None


def fetch_upstox_read_only(
    operation: str,
    request: Mapping[str, Any],
    *,
    enabled: bool,
    credential_present: bool,
    transport: Callable[[str, Mapping[str, Any]], Any] | None,
) -> UpstoxResult:
    """Execute an allow-listed read-only request, otherwise fail closed.

    Provider failure is represented as unavailable data so orchestration can
    continue with independent sources. No exception from Upstox is allowed to
    become a run-stopping dependency.
    """
    if operation not in READ_ONLY_OPERATIONS:
        return UpstoxResult(operation, False, error="operation is not allow-listed read-only")
    if not enabled:
        return UpstoxResult(operation, False, error="UPSTOX_ENABLED is false")
    if not credential_present:
        return UpstoxResult(operation, False, error="missing Upstox read-only credential")
    if transport is None:
        return UpstoxResult(operation, False, error="Upstox read-only transport unavailable")
    try:
        data = transport(operation, dict(request))
    except Exception as exc:  # provider/network errors must not stop IPO EDGE
        return UpstoxResult(operation, False, error=f"Upstox unavailable: {type(exc).__name__}")
    if data is None:
        return UpstoxResult(operation, False, error="Upstox returned no data")
    return UpstoxResult(operation, True, data=data)


def critical_evidence_satisfied(*, upstox_available: bool, independent_verified_sources: int) -> bool:
    """Upstox can supplement, never solely prove, critical evidence."""
    del upstox_available
    return independent_verified_sources >= 1
