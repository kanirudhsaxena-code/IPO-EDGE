from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ipoguru.in"
UA = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-IN,en;q=0.9"}


def _norm(value: str) -> str:
    value = value.lower().replace("sme ipo", "").replace("ipo", "")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _published_at(soup: BeautifulSoup) -> datetime | None:
    for attrs in (
        {"property": "article:published_time"},
        {"name": "article:published_time"},
        {"itemprop": "datePublished"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            parsed = _parse_datetime(tag.get("content"))
            if parsed:
                return parsed
    time_tag = soup.find("time")
    if time_tag:
        parsed = _parse_datetime(time_tag.get("datetime") or time_tag.get_text(" ", strip=True))
        if parsed:
            return parsed
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if isinstance(node, dict):
                parsed = _parse_datetime(node.get("datePublished"))
                if parsed:
                    return parsed
    return None


@lru_cache(maxsize=4)
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
    return tuple(reviews)


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


def fetch_consensus(company_name: str, timeout=20, evidence_cutoff: date | None = None):
    url = discover_review_url(company_name, timeout=timeout)
    if not url:
        return {"company_name": company_name, "found": False, "source_url": None, "historically_eligible": False}
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    published = _published_at(soup)
    eligible = False
    if published and evidence_cutoff:
        eligible = published.date() <= evidence_cutoff
    elif published and evidence_cutoff is None:
        eligible = True

    reviewed = re.search(r"reviewed by\s+(\d+)\s+analyst", text, re.I)
    subscribe = re.search(r"(\d+)\s+recommend subscribing", text, re.I)
    avoid = re.search(r"(\d+)\s+advise caution or avoidance", text, re.I)
    score = re.search(r"carrying a score of\s+(\d+(?:\.\d+)?)", text, re.I)

    return {
        "company_name": company_name,
        "found": True,
        "source_url": url,
        "published_at": published.isoformat() if published else None,
        "evidence_cutoff": evidence_cutoff.isoformat() if evidence_cutoff else None,
        "historically_eligible": eligible,
        "analyst_count": int(reviewed.group(1)) if (eligible and reviewed) else None,
        "subscribe_count": int(subscribe.group(1)) if (eligible and subscribe) else None,
        "avoid_count": int(avoid.group(1)) if (eligible and avoid) else None,
        "consensus_score": float(score.group(1)) if (eligible and score) else None,
    }
