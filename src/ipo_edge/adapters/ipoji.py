from __future__ import annotations

import re
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
        score = SequenceMatcher(None, target, label).ratio()
        candidates.append((score, urljoin(BASE, href), label))
    if not candidates:
        return None
    score, url, _ = max(candidates)
    return url if score >= 0.58 else None


def fetch_detail(company_name: str, timeout: int = 20) -> dict:
    url = discover_detail_url(company_name, timeout=timeout)
    if not url:
        return {"company_name": company_name, "source_url": None, "found": False}
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    def metric(label, suffix=r"%?"):
        return _num(re.escape(label) + r"[^0-9-]*(-?\d+(?:\.\d+)?)" + suffix, text)

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
        "gmp_pct": _num(r"GMP percentage[^0-9-]*(-?\d+(?:\.\d+)?)%", text),
        "raw_text": text[:50000],
    }
