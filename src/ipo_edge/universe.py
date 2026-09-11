from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import date, datetime

DATE_RANGE_RE = re.compile(r"(?P<open>\d{1,2} [A-Za-z]{3} 20\d{2})\s*[–-]\s*(?P<close>\d{1,2} [A-Za-z]{3} 20\d{2})")
GAIN_RE = re.compile(r"\((?P<sign>[+−-]?)(?P<pct>\d+(?:\.\d+)?)%\)")
PRICE_RE = re.compile(r"₹\s*([\d,]+(?:\.\d+)?)")

NON_EQUITY_MARKERS = ("reit", "invit", "investment trust")


@dataclass(frozen=True)
class NormalizedIPO:
    company_name: str
    segment: str
    issue_open_date: str
    issue_close_date: str
    issue_price: float | None
    discovery_source: str


def _parse_date(text: str) -> date:
    return datetime.strptime(text, "%d %b %Y").date()


def _price(text: str) -> float | None:
    matches = PRICE_RE.findall(text or "")
    if not matches:
        return None
    return float(matches[-1].replace(",", ""))


def _gain(text: str) -> float | None:
    m = GAIN_RE.search(text or "")
    if not m:
        return None
    value = float(m.group("pct"))
    if m.group("sign") in {"−", "-"}:
        value *= -1
    return value


def is_equity_ipo(row: dict) -> bool:
    name = row["company_name"].lower()
    return not any(marker in name for marker in NON_EQUITY_MARKERS)


def normalize_row(row: dict) -> tuple[dict, dict | None] | None:
    if not is_equity_ipo(row):
        return None
    m = DATE_RANGE_RE.search(row.get("issue_dates_text", ""))
    if not m:
        return None
    open_date = _parse_date(m.group("open"))
    close_date = _parse_date(m.group("close"))
    issue_price = _price(row.get("issue_price_text", ""))
    core = NormalizedIPO(
        company_name=row["company_name"].strip(),
        segment=row["segment"],
        issue_open_date=open_date.isoformat(),
        issue_close_date=close_date.isoformat(),
        issue_price=issue_price,
        discovery_source=row["discovery_source"],
    )
    gain = _gain(row.get("listing_text", ""))
    outcome = None if gain is None else {
        "company_name": core.company_name,
        "issue_open_date": core.issue_open_date,
        "listing_gain_percent": gain,
        "discovery_source": row["discovery_source"],
        "verification_status": "DISCOVERY_ONLY",
    }
    return asdict(core), outcome


def normalize_universe(rows: list[dict], start: date, end: date) -> tuple[list[dict], list[dict]]:
    core, outcomes = [], []
    for row in rows:
        normalized = normalize_row(row)
        if not normalized:
            continue
        ipo, outcome = normalized
        opened = date.fromisoformat(ipo["issue_open_date"])
        if not start <= opened <= end:
            continue
        core.append(ipo)
        if outcome:
            outcomes.append(outcome)
    core.sort(key=lambda x: (x["issue_open_date"], x["company_name"]))
    outcomes.sort(key=lambda x: (x["issue_open_date"], x["company_name"]))
    return core, outcomes
