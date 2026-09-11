from __future__ import annotations

import json
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "component_rules_v1.0.json"


def load_rules():
    return json.loads(RULES_PATH.read_text())


def interpolate(points, value):
    pts = sorted((float(x), float(y)) for x, y in points)
    value = float(value)
    if value <= pts[0][0]:
        return pts[0][1]
    if value >= pts[-1][0]:
        return pts[-1][1]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if x1 <= value <= x2:
            ratio = (value - x1) / (x2 - x1)
            return y1 + ratio * (y2 - y1)
    raise ValueError(value)


def score_financial(roe=None, roce=None, debt_equity=None):
    r = load_rules()["financial_quality"]
    vals = []
    if roe is not None:
        vals.append(interpolate(r["roe_pct"], roe))
    if roce is not None:
        vals.append(interpolate(r["roce_pct"], roce))
    if debt_equity is not None:
        vals.append(interpolate(r["debt_equity"], debt_equity))
    return round(sum(vals) / len(vals), 4) if len(vals) >= 2 else None


def score_valuation(pe_post=None, peer_relative_score=None):
    if peer_relative_score is not None:
        return max(0.0, min(1.0, float(peer_relative_score)))
    if pe_post is None:
        return None
    return round(interpolate(load_rules()["valuation"]["pe_post"], pe_post), 4)


def score_institutional(qib_x=None, anchor_quality=None):
    if qib_x is None:
        return None
    q = interpolate(load_rules()["institutional_conviction"]["qib_x"], qib_x)
    if anchor_quality is None:
        return round(q, 4)
    a = max(0.0, min(1.0, float(anchor_quality)))
    return round(0.8 * q + 0.2 * a, 4)


def score_demand(total_x=None, nii_x=None, retail_x=None):
    if total_x is None or nii_x is None or retail_x is None:
        return None
    r = load_rules()["market_demand"]
    total = interpolate(r["total_x"], total_x)
    nii = interpolate(r["nii_x"], nii_x)
    retail = interpolate(r["retail_x"], retail_x)
    return round(0.5 * total + 0.3 * nii + 0.2 * retail, 4)


def score_analyst(subscribe_count=None, analyst_count=None):
    if not analyst_count or subscribe_count is None:
        return None
    subscribe_ratio = max(0.0, min(1.0, float(subscribe_count) / float(analyst_count)))
    depth = interpolate(load_rules()["analyst_consensus"]["coverage_depth"], analyst_count)
    return round(0.8 * subscribe_ratio + 0.2 * depth, 4)


def score_gmp(gmp_pct=None):
    if gmp_pct is None:
        return None
    return round(interpolate(load_rules()["gmp_confirmation"]["gmp_pct"], gmp_pct), 4)
