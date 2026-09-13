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

# Execution metadata extends the existing registry; scoring tiers above stay frozen.
@dataclass(frozen=True)
class Publication:
    name: str
    url: str
    source_type: str
    priority: int
    group: str
    segments: tuple[str, ...] = ('MAINBOARD', 'SME')
    calendar: bool = False

PUBLICATIONS = (
    Publication('BSE public issues', 'https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx', 'EXCHANGE', 2, 'BSE', calendar=True),
    Publication('BSE announcements', 'https://www.bseindia.com/corporates/ann.html', 'EXCHANGE', 2, 'BSE'),
    Publication('BSE SME offer documents', 'https://www.bsesme.com/PublicIssues/SMEIPODRHP.aspx', 'EXCHANGE', 2, 'BSE', ('SME',)),
    Publication('BSE SME RHP', 'https://www.bsesme.com/PublicIssues/RHP.aspx', 'EXCHANGE', 2, 'BSE', ('SME',)),
    Publication('NSE public issues', 'https://www.nseindia.com/market-data/all-upcoming-issues-ipo', 'EXCHANGE', 2, 'NSE', calendar=True),
    Publication('SEBI public issues', 'https://www.sebi.gov.in/filings/public-issues.html', 'OFFICIAL_REGULATORY', 1, 'SEBI'),
    Publication('IPO Markets calendar', 'https://ipomarkets.com/ipo-calendar/{month}-{year}', 'GMP_SPECIALIST', 5, 'IPOMARKETS', calendar=True),
    Publication('IPO Watch calendar', 'https://ipowatch.in/ipo-calendar-{month}-{year}/', 'GMP_SPECIALIST', 6, 'IPOWATCH', calendar=True),
    Publication('IPOJi', 'https://www.ipoji.com/', 'GMP_SPECIALIST', 5, 'IPOJI'),
    Publication('IPOGuru research', 'https://ipoguru.in/', 'BROKER_RESEARCH', 5, 'IPOGURU'),
    Publication('Economic Times IPO', 'https://economictimes.indiatimes.com/markets/ipos', 'REPUTABLE_SECONDARY', 4, 'ET'),
)

def publication_for_url(url):
    from urllib.parse import urlparse
    exact=next((p for p in PUBLICATIONS if p.url==url),None)
    if exact: return exact
    host = (urlparse(url).hostname or '').lower()
    for source in PUBLICATIONS:
        root = (urlparse(source.url).hostname or '').removeprefix('www.')
        if host == root or host.endswith('.'+root):
            return source
    return None
