from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

SOURCE_TIERS = {
    "sebi.gov.in": 1,
    "nseindia.com": 2,
    "bseindia.com": 2,
    "moneycontrol.com": 4,
    "economictimes.indiatimes.com": 4,
    "business-standard.com": 4,
    "livemint.com": 4,
    "reuters.com": 4,
    "chittorgarh.com": 5,
    "ipowatch.in": 6,
}

CRITICAL_BLOCKS = {"R2", "R3", "R4", "R6", "R7"}
ALL_BLOCKS = {f"R{i}" for i in range(1, 9)}


@dataclass(frozen=True)
class EvidenceItem:
    block: str
    field_name: str
    value_text: str
    source_url: str
    source_name: str
    retrieved_at: datetime
    published_at: datetime | None = None
    verification_status: str = "VERIFIED"
    numeric_value: float | None = None

    @property
    def source_tier(self) -> int:
        host = urlparse(self.source_url).netloc.lower().removeprefix("www.")
        for domain, tier in SOURCE_TIERS.items():
            if host == domain or host.endswith("." + domain):
                return tier
        return 9

    def allowed_at(self, checkpoint_time: datetime) -> bool:
        """No post-checkpoint evidence may enter a historical decision."""
        effective = self.published_at or self.retrieved_at
        return effective <= checkpoint_time


def filter_for_checkpoint(items: list[EvidenceItem], checkpoint_time: datetime) -> list[EvidenceItem]:
    return [e for e in items if e.allowed_at(checkpoint_time)]


def coverage(items: list[EvidenceItem]) -> dict[str, bool]:
    verified = {e.block for e in items if e.verification_status == "VERIFIED"}
    return {block: block in verified for block in sorted(ALL_BLOCKS)}


def critical_evidence_verified(items: list[EvidenceItem]) -> bool:
    c = coverage(items)
    return all(c[b] for b in CRITICAL_BLOCKS)
