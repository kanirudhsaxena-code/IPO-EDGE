"""EH-03 hardening-only shadow ingress for canonical IPO identity resolution.

This adapter is deliberately read-only and fail-closed. It cannot activate unless the
execution-hardening master switch and identity-resolver feature are enabled, shadow-only
mode is true, and production writes are disabled. It returns resolution diagnostics only;
it does not persist or mutate model/history data.
"""
from dataclasses import dataclass
from typing import Mapping, Iterable, Any


@dataclass(frozen=True)
class ShadowIdentityIngressResult:
    status: str
    canonical_id: str | None = None
    canonical_name: str | None = None
    matched_by: str | None = None
    reason: str | None = None


def _enabled(config: Mapping[str, Any]) -> tuple[bool, str | None]:
    rollback = config.get("rollback", {})
    features = config.get("features", {})
    invariants = config.get("invariants", {})
    if not config.get("shadow_only", False):
        return False, "SHADOW_ONLY_REQUIRED"
    if config.get("production_writes", True):
        return False, "PRODUCTION_WRITES_MUST_BE_DISABLED"
    if invariants.get("allow_model_changes", True):
        return False, "MODEL_CHANGES_MUST_BE_DISABLED"
    if not rollback.get("master_enabled", False):
        return False, "HARDENING_MASTER_DISABLED"
    if not features.get("identity_resolver", False):
        return False, "IDENTITY_RESOLVER_DISABLED"
    return True, None


def resolve_shadow_identity(config: Mapping[str, Any], resolver: Any, incoming: Any) -> ShadowIdentityIngressResult:
    """Resolve one live/shadow ingress identity without persistence or model effects."""
    enabled, reason = _enabled(config)
    if not enabled:
        return ShadowIdentityIngressResult(status="BYPASSED", reason=reason)

    duplicate_keys = resolver.duplicate_keys()
    if duplicate_keys:
        return ShadowIdentityIngressResult(status="CONFLICT", reason="CANONICAL_MAP_AMBIGUOUS")

    result = resolver.resolve(incoming)
    if result.status != "RESOLVED":
        return ShadowIdentityIngressResult(status=result.status, reason="IDENTITY_NOT_UNIQUELY_RESOLVED")
    return ShadowIdentityIngressResult(
        status="RESOLVED",
        canonical_id=result.canonical_id,
        canonical_name=result.canonical_name,
        matched_by=result.matched_by,
    )
