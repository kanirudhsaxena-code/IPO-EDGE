from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ipoguru.in"
UA = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-IN,en;q=0.9"}


def _norm(value: str) -> str:
    value = value.lower().replace("sme ipo", "").replace("ipo", "")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _sitemap_urls(timeout=20):
    pending = [BASE + "/sitemap.xml"]
    seen = set()
    reviews = []
    while pending and len(seen) < 25:
        url = pending.pop(0)
        if url in seen:
            continue
        seen.add(url)
        r = requests.get(url, headers=UA, timeout=timeout)
        if not r.ok:
            continue
        try:
            root = ET.fromstring(r.text)
        except ET.ParseError:
            continue
        locs = [el.text for el in root.iter() if el.tag.endswith("loc") and el.text]
        for loc in locs:
            if "/ipo-review/" in loc:
                reviews.append(loc)
            elif "sitemap" in urlparse(loc).path:
                pending.append(loc)
    return reviews


def discover_review_url(company_name: str, timeout=20):
    target = _norm(company_name)
    candidates = []
    for url in _sitemap_urls(timeout=timeout):
        slug = url.rstrip("/").split("/")[-1]
        score = SequenceMatcher(None, target, _norm(slug.replace("-", " "))).ratio()
        candidates.append((score, url))
    if not candidates:
        return None
    score, url = max(candidates)
    return url if score >= 0.55 else None


def fetch_consensus(company_name: str, timeout=20):
    url = discover_review_url(company_name, timeout=timeout)
    if not url:
        return {"company_name": company_name, "found": False, "source_url": None}
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
    reviewed = re.search(r"reviewed by\s+(\d+)\s+analyst", text, re.I)
    subscribe = re.search(r"(\d+)\s+recommend subscribing", text, re.I)
    avoid = re.search(r"(\d+)\s+advise caution or avoidance", text, re.I)
    score = re.search(r"carrying a score of\s+(\d+(?:\.\d+)?)", text, re.I)
    return {
        "company_name": company_name,
        "found": True,
        "source_url": url,
        "analyst_count": int(reviewed.group(1)) if reviewed else None,
        "subscribe_count": int(subscribe.group(1)) if subscribe else None,
        "avoid_count": int(avoid.group(1)) if avoid else None,
        "consensus_score": float(score.group(1)) if score else None,
    }
