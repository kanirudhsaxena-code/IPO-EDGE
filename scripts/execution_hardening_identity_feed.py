"""EH-03 read-only canonical-map feed for hardening shadow ingress.

Builds a deterministic CanonicalIPO map from already-fetched live/shadow provider
rows. This module performs no network or database writes and never mutates model
or historical data. Conflicting canonical IDs fail closed before ingress.
"""
from collections import defaultdict
from typing import Iterable, Mapping, Any

from execution_hardening_identity import CanonicalIPO, IdentityResolver


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def build_canonical_map(rows: Iterable[Mapping[str, Any]]) -> tuple[CanonicalIPO, ...]:
    """Build canonical records from live/shadow rows without fuzzy inference.

    Each row must carry an explicit canonical_id and canonical_name. Optional
    provider identifiers/aliases are additive evidence only. A canonical_id with
    conflicting canonical names fails closed.
    """
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        canonical_id = _clean(row.get("canonical_id"))
        canonical_name = _clean(row.get("canonical_name"))
        if not canonical_id or not canonical_name:
            raise ValueError("canonical feed row missing canonical_id/canonical_name")
        entry = grouped.setdefault(canonical_id, {
            "names": set(), "isins": set(), "exchange_ids": set(),
            "upstox_ids": set(), "aliases": set(),
        })
        entry["names"].add(canonical_name)
        for key, bucket in (("isin", "isins"), ("exchange_id", "exchange_ids"),
                            ("upstox_id", "upstox_ids")):
            value = _clean(row.get(key))
            if value:
                entry[bucket].add(value)
        aliases = row.get("aliases") or ()
        if isinstance(aliases, str):
            aliases = (aliases,)
        entry["aliases"].update(_clean(v) for v in aliases if _clean(v))

    records = []
    for canonical_id in sorted(grouped):
        entry = grouped[canonical_id]
        if len(entry["names"]) != 1:
            raise ValueError(f"conflicting canonical names for {canonical_id}")
        isins = sorted(entry["isins"])
        if len(isins) > 1:
            raise ValueError(f"conflicting ISINs for {canonical_id}")
        records.append(CanonicalIPO(
            canonical_id=canonical_id,
            canonical_name=next(iter(entry["names"])),
            isin=isins[0] if isins else None,
            exchange_ids=tuple(sorted(entry["exchange_ids"])),
            upstox_ids=tuple(sorted(entry["upstox_ids"])),
            aliases=tuple(sorted(entry["aliases"])),
        ))

    resolver = IdentityResolver(records)
    if resolver.duplicate_keys():
        raise ValueError("canonical feed contains ambiguous identity keys")
    return tuple(records)


def build_shadow_resolver(rows: Iterable[Mapping[str, Any]]) -> IdentityResolver:
    """Return a validated resolver suitable for hardening-only shadow ingress."""
    return IdentityResolver(build_canonical_map(rows))
