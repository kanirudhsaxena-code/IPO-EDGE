"""Execution-only observability for IPO EDGE V1.1 hardening.

No model scoring, grading, NV gating, recommendation, or persistence occurs here.
Canonical efficacy is intentionally kept separate from execution diagnostics.
"""
from dataclasses import dataclass, asdict
from typing import Iterable, Mapping, Any

VALID_DISPOSITIONS = {"COMPLETE", "NV", "PARTIAL", "UNRESOLVED"}

@dataclass(frozen=True)
class IPODiagnostic:
    canonical_id: str
    unresolved_blocks: tuple[str, ...]
    attempted_sources: tuple[str, ...]
    conflicts: tuple[str, ...]
    identity_status: str
    disposition: str

    def __post_init__(self):
        if not self.canonical_id.strip():
            raise ValueError("canonical_id required")
        if self.disposition not in VALID_DISPOSITIONS:
            raise ValueError("invalid execution disposition")


def build_execution_diagnostics(*, expected: int, reconciled: int, researched: int,
                                ipos: Iterable[IPODiagnostic],
                                source_health: Mapping[str, Any],
                                upstox_available: bool) -> dict[str, Any]:
    """Return execution diagnostics only; never mixes in framework efficacy."""
    counts = {"expected": expected, "reconciled": reconciled, "researched": researched,
              "complete": 0, "nv": 0, "partial": 0}
    if min(expected, reconciled, researched) < 0:
        raise ValueError("counts cannot be negative")
    if reconciled > expected or researched > reconciled:
        raise ValueError("execution counts must be monotonic")
    rows = []
    for ipo in ipos:
        rows.append(asdict(ipo))
        if ipo.disposition == "COMPLETE": counts["complete"] += 1
        elif ipo.disposition == "NV": counts["nv"] += 1
        elif ipo.disposition == "PARTIAL": counts["partial"] += 1
    if len(rows) > researched:
        raise ValueError("IPO diagnostics exceed researched count")
    return {
        "kind": "EXECUTION_DIAGNOSTICS",
        "counts": counts,
        "ipos": rows,
        "provider_health": {"sources": dict(source_health), "upstox_available": bool(upstox_available)},
        "framework_efficacy": None,
        "model_policy_changed": False,
    }


def canonical_efficacy_view(efficacy: Mapping[str, Any]) -> dict[str, Any]:
    """Explicitly separate canonical efficacy payload from execution/replay diagnostics."""
    return {"kind": "CANONICAL_EFFICACY", "efficacy": dict(efficacy), "execution_diagnostics": None}
