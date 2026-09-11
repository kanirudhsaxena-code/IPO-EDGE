from __future__ import annotations

import re
from datetime import date, datetime
from difflib import SequenceMatcher
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ipoji.com"
LIST_URL = BASE + "/ipo-list?year=2026"
UA = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-IN,en;q=0.9"}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _num(pattern: str, text: str):
    m = re.search(pattern, text, flags=re.I)
    return float(m.group(1).replace(",", "")) if m else None


def _parse_date(value: str) -> date | None:
    value = re.sub(r"\s+", " ", value.strip())
    for fmt in ("%d %b %Y", "%d %B %Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def discover_detail_url(company_name: str, timeout: int = 20) -> str | None:
    r = requests.get(LIST_URL, headers=UA, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    target = _norm(company_name)
    candidates = []
    for a in soup.select('a[href*="/ipo/"]'):
        label = _norm(a.get_text(" ", strip=True))
        href = a.get("href")
        if not label or not href:
            continue
        candidates.append((SequenceMatcher(None, target, label).ratio(), urljoin(BASE, href)))
    if not candidates:
        return None
    score, url = max(candidates)
    return url if score >= 0.58 else None


def _historical_gmp(soup: BeautifulSoup, cutoff: date | None) -> tuple[float | None, str | None]:
    """Return only a GMP observation whose displayed date is on/before cutoff.

    Never falls back to the page's current/latest GMP during a historical run.
    """
    if cutoff is None:
        return None, None
    candidates: list[tuple[date, float]] = []
    for row in soup.select("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.select("th,td")]
        if len(cells) < 2:
            continue
        row_date = next((_parse_date(c) for c in cells if _parse_date(c)), None)
        if not row_date or row_date > cutoff:
            continue
        joined = " | ".join(cells)
        pct = _num(r"(-?\d+(?:\.\d+)?)\s*%", joined)
        if pct is not None:
            candidates.append((row_date, pct))
    if not candidates:
        return None, None
    d, pct = max(candidates, key=lambda x: x[0])
    return pct, d.isoformat()


def fetch_detail(company_name: str, timeout: int = 20, evidence_cutoff: date | None = None) -> dict:
    url = discover_detail_url(company_name, timeout=timeout)
    if not url:
        return {"company_name": company_name, "source_url": None, "found": False}
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    gmp_pct, gmp_observed_date = _historical_gmp(soup, evidence_cutoff)

    return {
        "company_name": company_name,
        "source_url": url,
        "found": True,
        "qib_x": _num(r"Qualified Institutional Buyers \(QIBs\)\s*(\d+(?:\.\d+)?)x", text),
        "nii_x": _num(r"Non-Institutional Investors \(NIIs\)\s*(\d+(?:\.\d+)?)x", text),
        "retail_x": _num(r"(?:Retail|Individual)\s*(\d+(?:\.\d+)?)x", text),
        "total_x": _num(r"Total\s*(\d+(?:\.\d+)?)x", text),
        "pe_post": _num(r"P/E Post IPO[^0-9]*(\d+(?:\.\d+)?)", text),
        "roe_pct": _num(r"ROE[^0-9]*(\d+(?:\.\d+)?)%", text),
        "roce_pct": _num(r"ROCE[^0-9]*(\d+(?:\.\d+)?)%", text),
        "debt_equity": _num(r"Debt / Equity[^0-9]*(\d+(?:\.\d+)?)", text),
        "ronw_pct": _num(r"RoNW[^0-9]*(\d+(?:\.\d+)?)%", text),
        "gmp_pct": gmp_pct,
        "gmp_observed_date": gmp_observed_date,
        "evidence_cutoff": evidence_cutoff.isoformat() if evidence_cutoff else None,
        "raw_text": text[:50000],
    }
