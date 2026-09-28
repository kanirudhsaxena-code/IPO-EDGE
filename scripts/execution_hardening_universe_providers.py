"""Fail-closed EH-02 provider adapter layer.

This module normalizes already-fetched provider records into the pure universe
reconciler. It performs no scoring/model work and no database writes. Network
fetching remains outside this module so provider credentials and transport can
be isolated and feature-flagged.
"""
from dataclasses import dataclass
from typing import Iterable, Mapping, Any

SUPPORTED_SOURCES = {"NSE", "BSE", "SEBI", "SPECIALIST", "UPSTOX"}
SUPPORTED_SEGMENTS = {"MAINBOARD", "SME"}


@dataclass(frozen=True)
class NormalizedRecord:
    source: str
    segment: str
    identity: str


@dataclass(frozen=True)
class ProviderBatch:
    source: str
    segment: str
    enumerated: bool
    parse_ok: bool
    records: tuple[NormalizedRecord, ...]
    error: str | None = None


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_records(source: str, segment: str, records: Iterable[Mapping[str, Any]], *,
                      enumerated: bool, parse_ok: bool, identity_keys=("isin", "exchange_id", "ipo_id", "name")) -> ProviderBatch:
    """Normalize a provider enumeration without inventing missing identities.

    A malformed row makes the batch fail closed. Identity precedence is
    deterministic and deliberately contains no fuzzy matching; canonical alias
    resolution belongs to EH-03.
    """
    source = source.upper()
    segment = segment.upper()
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"unsupported source: {source}")
    if segment not in SUPPORTED_SEGMENTS:
        raise ValueError(f"unsupported segment: {segment}")
    if not enumerated or not parse_ok:
        return ProviderBatch(source, segment, enumerated, parse_ok, (), "provider enumeration/parse incomplete")

    out = []
    for row in records:
        identity = next((_clean(row.get(k)) for k in identity_keys if _clean(row.get(k))), "")
        if not identity:
            return ProviderBatch(source, segment, True, False, tuple(out), "record missing stable identity")
        out.append(NormalizedRecord(source, segment, identity))
    return ProviderBatch(source, segment, True, True, tuple(out))


def source_union(batches: Iterable[ProviderBatch], *, upstox_enabled: bool = False) -> dict[str, tuple[NormalizedRecord, ...]]:
    """Union healthy provider batches by segment; Upstox is opt-in and non-essential."""
    union = {"MAINBOARD": [], "SME": []}
    for batch in batches:
        if batch.source == "UPSTOX" and not upstox_enabled:
            continue
        if not (batch.enumerated and batch.parse_ok):
            continue
        union[batch.segment].extend(batch.records)
    return {segment: tuple(records) for segment, records in union.items()}
