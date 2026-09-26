"""Execution-hardening universe reconciliation (EH-02).

Pure infrastructure: this module does not score IPOs, alter NV rules, or write
historical data. It reconciles independently enumerated source observations and
fails closed when completeness cannot be demonstrated.
"""
from dataclasses import dataclass, field
from typing import Iterable

SEGMENTS = {"MAINBOARD", "SME"}
OFFICIAL_SOURCES = {"NSE", "BSE", "SEBI"}


@dataclass(frozen=True)
class Observation:
    source: str
    segment: str
    identity: str


@dataclass(frozen=True)
class SourceRun:
    source: str
    segment: str
    enumerated: bool
    parse_ok: bool
    observations: tuple[Observation, ...] = field(default_factory=tuple)

    @property
    def healthy(self) -> bool:
        return self.enumerated and self.parse_ok


@dataclass(frozen=True)
class SegmentResult:
    segment: str
    status: str
    identities: frozenset[str]
    healthy_sources: tuple[str, ...]
    discrepancies: dict[str, tuple[str, ...]]


def reconcile_segment(segment: str, runs: Iterable[SourceRun]) -> SegmentResult:
    """Union healthy enumerations and require independent completeness evidence.

    COMPLETE requires at least two healthy independent enumerations, including
    at least one official source. An empty universe can be COMPLETE only when
    two healthy official sources independently enumerate it as empty. This
    prevents one outage/empty parse from silently defining the universe.
    """
    if segment not in SEGMENTS:
        raise ValueError(f"unsupported segment: {segment}")
    scoped = [r for r in runs if r.segment == segment]
    healthy = [r for r in scoped if r.healthy]
    union = frozenset(o.identity for r in healthy for o in r.observations)
    healthy_names = tuple(sorted({r.source for r in healthy}))
    official_healthy = {r.source for r in healthy if r.source in OFFICIAL_SOURCES}

    by_source = {
        r.source: frozenset(o.identity for o in r.observations)
        for r in healthy
    }
    discrepancies = {
        source: tuple(sorted(union - identities))
        for source, identities in sorted(by_source.items())
        if union - identities
    }

    if not healthy:
        status = "FAILED"
    elif not union:
        status = "COMPLETE" if len(official_healthy) >= 2 else "PARTIAL"
    elif len(healthy_names) >= 2 and official_healthy:
        status = "COMPLETE"
    else:
        status = "PARTIAL"

    return SegmentResult(segment, status, union, healthy_names, discrepancies)


def reconcile_universe(runs: Iterable[SourceRun]) -> dict[str, SegmentResult]:
    """Reconcile Mainboard and SME separately; never infer one from the other."""
    runs = tuple(runs)
    return {segment: reconcile_segment(segment, runs) for segment in sorted(SEGMENTS)}
