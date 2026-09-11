from __future__ import annotations

import re
from datetime import date, datetime
from difflib import SequenceMatcher
from functools import lru_cache
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ipoji.com"
LIST_URL = BASE + "/ipo-list?year=2026"
UA = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-IN,en;q=0.9"}
OFFICIAL_DOC_DOMAINS = ("sebi.gov.in", "nseindia.com", "bseindia.com")
OFFER_DOC_TOKENS = ("rhp", "drhp", "prospectus", "offer document", "red herring")


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


def _series_from_row(soup: BeautifulSoup, label: str) -> list[float]:
    target = label.lower()
    for row in soup.select("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.select("th,td")]
        if not cells or target not in cells[0].lower():
            continue
        vals = []
        for c in cells[1:]:
            m = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?", c)
            if m:
                vals.append(float(m.group(0).replace(",", "")))
        return vals
    return []


def _official_document_url(soup: BeautifulSoup) -> str | None:
    candidates = []
    for a in soup.select("a[href]"):
        href = urljoin(BASE, a.get("href"))
        label = a.get_text(" ", strip=True).lower()
        href_l = href.lower()
        host = urlparse(href).netloc.lower().removeprefix("www.")
        official = any(host == d or host.endswith("." + d) for d in OFFICIAL_DOC_DOMAINS)
        doc_like = any(token in label or token.replace(" ", "") in href_l.replace("_", "").replace("-", "") for token in OFFER_DOC_TOKENS)
        if official and doc_like:
            priority = 0 if (("rhp" in label or "rhp" in href_l) and "drhp" not in label and "drhp" not in href_l) else 1
            candidates.append((priority, href))
    return min(candidates)[1] if candidates else None


@lru_cache(maxsize=4)
def _list_candidates(timeout: int = 20) -> tuple[tuple[str, str], ...]:
    r = requests.get(LIST_URL, headers=UA, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    candidates = []
    for a in soup.select('a[href*="/ipo/"]'):
        label = _norm(a.get_text(" ", strip=True))
        href = a.get("href")
        if label and href:
            candidates.append((label, urljoin(BASE, href)))
    return tuple(candidates)


def discover_detail_url(company_name: str, timeout: int = 20) -> str | None:
    target = _norm(company_name)
    candidates = [(SequenceMatcher(None, target, label).ratio(), url) for label, url in _list_candidates(timeout)]
    if not candidates:
        return None
    score, url = max(candidates)
    return url if score >= 0.58 else None


def _historical_gmp(soup: BeautifulSoup, cutoff: date | None) -> tuple[float | None, str | None]:
    if cutoff is None:
        return None, None
    candidates: list[tuple[date, float]] = []
    for row in soup.select("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.select("th,td")]
        if len(cells) < 2:
            continue
        parsed_dates = [_parse_date(c) for c in cells]
        row_date = next((d for d in parsed_dates if d), None)
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
    official_document_url = _official_document_url(soup)

    incorporation_year = None
    m = re.search(r"incorporated\s+(?:in|on)\s+(?:[A-Za-z]+\s+)?(19\d{2}|20\d{2})", text, flags=re.I)
    if m:
        incorporation_year = int(m.group(1))

    revenue_history = _series_from_row(soup, "Revenue")
    pat_history = _series_from_row(soup, "Profit After Tax")
    latest_revenue_cr = revenue_history[0] if revenue_history else None
    profitable_ratio = None
    if pat_history:
        profitable_ratio = sum(1 for v in pat_history if v > 0) / len(pat_history)

    company_age_years = None
    if incorporation_year and evidence_cutoff:
        company_age_years = max(0, evidence_cutoff.year - incorporation_year)

    return {
        "company_name": company_name,
        "source_url": url,
        "found": True,
        "official_document_url": official_document_url,
        "r4_document_verified": official_document_url is not None,
        "qib_x": _num(r"Qualified Institutional Buyers \(QIBs\)\s*(\d+(?:\.\d+)?)x", text),
        "nii_x": _num(r"Non-Institutional Investors \(NIIs\)\s*(\d+(?:\.\d+)?)x", text),
        "retail_x": _num(r"(?:Retail|Individual)\s*(\d+(?:\.\d+)?)x", text),
        "total_x": _num(r"Total\s*(\d+(?:\.\d+)?)x", text),
        "pe_post": _num(r"P/E Post IPO[^0-9]*(\d+(?:\.\d+)?)", text),
        "roe_pct": _num(r"ROE[^0-9]*(\d+(?:\.\d+)?)%", text),
        "roce_pct": _num(r"ROCE[^0-9]*(\d+(?:\.\d+)?)%", text),
        "debt_equity": _num(r"Debt / Equity[^0-9]*(\d+(?:\.\d+)?)", text),
        "ronw_pct": _num(r"RoNW[^0-9]*(\d+(?:\.\d+)?)%", text),
        "incorporation_year": incorporation_year,
        "company_age_years": company_age_years,
        "latest_revenue_cr": latest_revenue_cr,
        "revenue_history_cr": revenue_history,
        "pat_history_cr": pat_history,
        "profitable_period_ratio": round(profitable_ratio, 4) if profitable_ratio is not None else None,
        "gmp_pct": gmp_pct,
        "gmp_observed_date": gmp_observed_date,
        "evidence_cutoff": evidence_cutoff.isoformat() if evidence_cutoff else None,
        "raw_text": text[:50000],
    }
