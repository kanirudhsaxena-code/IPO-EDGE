from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

import requests
from bs4 import BeautifulSoup

NSE_UPCOMING_URL = "https://www.nseindia.com/market-data/all-upcoming-issues-ipo"


@dataclass(frozen=True)
class DiscoveredIPO:
    company_name: str
    issue_start_date: date | None
    issue_end_date: date | None
    status: str
    security_type: str | None = None
    subscription_x: float | None = None
    source_url: str = NSE_UPCOMING_URL


def _parse_date(value: str) -> date | None:
    value = value.strip()
    if not value or value == "-":
        return None
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def discover_nse_public_issues(timeout: int = 20) -> list[DiscoveredIPO]:
    """Best-effort parser for NSE's public IPO table.

    The provider deliberately returns only what is directly visible in the public
    page and never manufactures missing fields. The research layer enriches these
    records from official documents and other frozen source tiers.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; IPO-EDGE/1.0; +https://github.com/kanirudhsaxena-code/IPO-EDGE)",
        "Accept-Language": "en-US,en;q=0.9",
    }
    response = requests.get(NSE_UPCOMING_URL, headers=headers, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    results: list[DiscoveredIPO] = []
    for row in soup.select("table tbody tr"):
        cells = [c.get_text(" ", strip=True) for c in row.select("td")]
        if len(cells) < 5:
            continue
        sub = None
        if len(cells) >= 8:
            try:
                sub = float(cells[-1].replace(",", ""))
            except ValueError:
                pass
        results.append(
            DiscoveredIPO(
                company_name=cells[0],
                security_type=cells[1] or None,
                issue_start_date=_parse_date(cells[2]),
                issue_end_date=_parse_date(cells[3]),
                status=cells[4] or "UNKNOWN",
                subscription_x=sub,
            )
        )
    return results
