from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime

import requests
from bs4 import BeautifulSoup

ROW_RE = re.compile(
    r"(?P<company>.+?)(?P<segment>Mainboard|SME)\s+\|\s+"
    r"(?P<status>[^|]+)\|\s+₹?(?P<price>[^|]+)\|\s+"
    r"(?P<gmp>[^|]+)\|\s+(?P<sub>[^|]+)\|\s+"
    r"(?P<dates>[^|]+)\|\s+(?P<listing>.+)$"
)


@dataclass(frozen=True)
class UniverseRow:
    company_name: str
    segment: str
    issue_price_text: str
    subscription_text: str
    issue_dates_text: str
    listing_text: str
    discovery_source: str


def parse_calendar(url: str, timeout: int = 20) -> list[UniverseRow]:
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 IPO-EDGE/1.0"}, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rows: list[UniverseRow] = []
    for tr in soup.select("table tbody tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.select("td")]
        if len(cells) < 7:
            continue
        company_cell = cells[0]
        segment = "SME" if "SME" in company_cell else "MAINBOARD" if "Mainboard" in company_cell else None
        if not segment:
            continue
        company = company_cell.replace("Mainboard", "").replace("SME", "").strip()
        rows.append(
            UniverseRow(
                company_name=company,
                segment=segment,
                issue_price_text=cells[2],
                subscription_text=cells[4],
                issue_dates_text=cells[5],
                listing_text=cells[6],
                discovery_source=url,
            )
        )
    return rows


def build_universe(urls: list[str]) -> list[dict]:
    output: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for url in urls:
        for row in parse_calendar(url):
            key = (row.company_name.lower(), row.issue_dates_text)
            if key in seen:
                continue
            seen.add(key)
            output.append(asdict(row))
    return output
