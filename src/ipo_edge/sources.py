from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourcePolicy:
    name: str
    domain: str
    tier: int
    blocks: tuple[str, ...]
    role: str


SOURCES = (
    SourcePolicy("SEBI", "sebi.gov.in", 1, ("R1","R2","R3","R4"), "PRIMARY"),
    SourcePolicy("NSE", "nseindia.com", 2, ("R6","R7"), "PRIMARY"),
    SourcePolicy("BSE", "bseindia.com", 2, ("R6","R7"), "PRIMARY"),
    SourcePolicy("IPOJi", "ipoji.com", 5, ("R1","R2","R3","R4","R6","R7"), "STRUCTURED_SECONDARY"),
    SourcePolicy("IPOGuru", "ipoguru.in", 5, ("R5",), "ANALYST_AGGREGATOR"),
    SourcePolicy("Economic Times IPO", "economictimes.indiatimes.com", 4, ("R6","R7"), "CROSS_CHECK"),
    SourcePolicy("IPO Markets", "ipomarkets.com", 5, ("R7",), "DISCOVERY_ONLY"),
)


def policies_for_block(block: str):
    return [s for s in SOURCES if block in s.blocks]
