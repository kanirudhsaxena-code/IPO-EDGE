"""EH-03 canonical identity resolver.

Execution-only infrastructure. Historical stored names are inputs, never rewritten.
Resolution precedence is ISIN, exchange/Upstox identifier, then exact canonical
name/explicit alias. Ambiguity fails closed; no fuzzy matching is performed.
"""
from dataclasses import dataclass, field
from typing import Iterable
import re


def _norm(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", (value or "").upper()).strip()


@dataclass(frozen=True)
class CanonicalIPO:
    canonical_id: str
    canonical_name: str
    isin: str | None = None
    exchange_ids: tuple[str, ...] = field(default_factory=tuple)
    upstox_ids: tuple[str, ...] = field(default_factory=tuple)
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IdentityInput:
    name: str | None = None
    isin: str | None = None
    exchange_id: str | None = None
    upstox_id: str | None = None


@dataclass(frozen=True)
class IdentityResult:
    status: str
    canonical_id: str | None
    canonical_name: str | None
    matched_by: str | None
    candidates: tuple[str, ...] = field(default_factory=tuple)


class IdentityResolver:
    def __init__(self, records: Iterable[CanonicalIPO]):
        self.records = tuple(records)
        self._indexes = {key: {} for key in ("isin", "exchange_id", "upstox_id", "name")}
        for record in self.records:
            self._add("isin", record.isin, record)
            for value in record.exchange_ids:
                self._add("exchange_id", value, record)
            for value in record.upstox_ids:
                self._add("upstox_id", value, record)
            self._add("name", record.canonical_name, record)
            for value in record.aliases:
                self._add("name", value, record)

    def _add(self, kind, value, record):
        key = _norm(value)
        if key:
            self._indexes[kind].setdefault(key, []).append(record)

    def resolve(self, incoming: IdentityInput) -> IdentityResult:
        for kind, value in (("isin", incoming.isin), ("exchange_id", incoming.exchange_id),
                            ("upstox_id", incoming.upstox_id), ("name", incoming.name)):
            key = _norm(value)
            if not key:
                continue
            matches = self._indexes[kind].get(key, [])
            unique = {m.canonical_id: m for m in matches}
            if len(unique) == 1:
                record = next(iter(unique.values()))
                return IdentityResult("RESOLVED", record.canonical_id, record.canonical_name, kind)
            if len(unique) > 1:
                return IdentityResult("CONFLICT", None, None, kind, tuple(sorted(unique)))
        return IdentityResult("UNRESOLVED", None, None, None)

    def duplicate_keys(self) -> dict[str, tuple[str, ...]]:
        """Return ambiguous keys so duplicates are caught before persistence."""
        out = {}
        for kind, index in self._indexes.items():
            for key, records in index.items():
                ids = tuple(sorted({r.canonical_id for r in records}))
                if len(ids) > 1:
                    out[f"{kind}:{key}"] = ids
        return out
