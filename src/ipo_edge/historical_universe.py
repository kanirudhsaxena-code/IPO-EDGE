from __future__ import annotations

from dataclasses import asdict, dataclass

import requests
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class UniverseRow:
    company_name: str
    segment: str
    issue_price_text: str
    subscription_text: str
    issue_dates_text: str
    listing_text: str
    discovery_source: str


def _segment(text: str) -> str | None:
    low = text.lower()
    if "sme" in low and "mainboard" not in low:
        return "SME"
    if "mainboard" in low:
        return "MAINBOARD"
    return None


def parse_calendar(url: str, timeout: int = 20) -> list[UniverseRow]:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9",
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rows: list[UniverseRow] = []

    # Some archive pages omit an explicit <tbody>, so scan every table row.
    for tr in soup.select("table tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if len(cells) < 7 or cells[0].lower().startswith("company"):
            continue
        row_text = " ".join(cells[:2])
        segment = _segment(row_text)
        if not segment:
            continue
        company = cells[0].replace("Mainboard", "").replace("SME", "").strip()
        if not company:
            continue
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
    failures: list[str] = []
    for url in urls:
        rows = parse_calendar(url)
        if not rows:
            failures.append(url)
        for row in rows:
            key = (row.company_name.lower(), row.issue_dates_text)
            if key in seen:
                continue
            seen.add(key)
            output.append(asdict(row))
    if not output:
        raise RuntimeError("Historical IPO discovery returned zero rows; sources/parsing require repair")
    if failures:
        print("WARNING: no rows from:", ", ".join(failures))
    return output
