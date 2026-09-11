from __future__ import annotations

RULES = {
    "business_quality": {
        "company_age_years": [[0,0.20],[3,0.40],[5,0.55],[10,0.75],[15,0.90],[25,1.00]],
        "latest_revenue_cr": [[0,0.15],[10,0.30],[25,0.45],[50,0.60],[100,0.75],[250,0.90],[500,1.00]],
        "profitable_period_ratio": [[0,0.00],[0.50,0.40],[0.75,0.70],[1.00,1.00]],
    },
    "financial_quality": {
        "roe_pct": [[0,0.20],[10,0.40],[15,0.60],[20,0.75],[25,0.90],[30,1.00]],
        "roce_pct": [[0,0.20],[10,0.40],[15,0.60],[20,0.75],[25,0.90],[30,1.00]],
        "debt_equity": [[0,1.00],[0.25,0.90],[0.50,0.75],[1.00,0.55],[1.50,0.35],[2.00,0.20]],
    },
    "valuation": {
        "pe_post": [[10,0.95],[15,0.90],[20,0.80],[25,0.70],[35,0.55],[50,0.35],[75,0.20]],
    },
    "institutional_conviction": {
        "qib_x": [[0,0.10],[1,0.25],[3,0.40],[10,0.60],[25,0.75],[50,0.85],[100,0.95],[200,1.00]],
    },
    "market_demand": {
        "total_x": [[0,0.10],[1,0.25],[3,0.40],[10,0.60],[25,0.75],[50,0.85],[100,0.95],[200,1.00]],
        "nii_x": [[0,0.10],[1,0.25],[3,0.40],[10,0.60],[25,0.75],[50,0.85],[100,0.95],[200,1.00]],
        "retail_x": [[0,0.10],[1,0.25],[3,0.40],[10,0.60],[25,0.75],[50,0.85],[100,0.95],[200,1.00]],
    },
    "analyst_consensus": {
        "coverage_depth": [[0,0.00],[1,0.55],[3,0.70],[5,0.80],[10,0.90],[15,1.00]],
    },
    "sector_ipo_environment": {
        "nifty_20d_return_pct": [[-12,0.00],[-8,0.20],[-5,0.35],[0,0.60],[3,0.75],[6,0.90],[10,1.00]],
        "nifty_20d_vol_pct": [[10,1.00],[15,0.90],[20,0.75],[25,0.60],[30,0.40],[40,0.15],[50,0.00]],
    },
    "gmp_confirmation": {
        "gmp_pct": [[-10,0.00],[0,0.20],[5,0.35],[10,0.50],[20,0.70],[30,0.85],[40,0.95],[50,1.00]],
    },
}


def load_rules():
    return RULES


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


def score_business(company_age_years=None, latest_revenue_cr=None, profitable_period_ratio=None):
    r = RULES["business_quality"]
    vals = []
    if company_age_years is not None:
        vals.append((0.35, interpolate(r["company_age_years"], company_age_years)))
    if latest_revenue_cr is not None:
        vals.append((0.35, interpolate(r["latest_revenue_cr"], latest_revenue_cr)))
    if profitable_period_ratio is not None:
        vals.append((0.30, interpolate(r["profitable_period_ratio"], profitable_period_ratio)))
    if len(vals) < 2:
        return None
    weight_sum = sum(w for w, _ in vals)
    return round(sum(w * v for w, v in vals) / weight_sum, 4)


def score_financial(roe=None, roce=None, debt_equity=None):
    r = RULES["financial_quality"]
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
    return round(interpolate(RULES["valuation"]["pe_post"], pe_post), 4)


def score_institutional(qib_x=None, anchor_quality=None):
    if qib_x is None:
        return None
    q = interpolate(RULES["institutional_conviction"]["qib_x"], qib_x)
    if anchor_quality is None:
        return round(q, 4)
    a = max(0.0, min(1.0, float(anchor_quality)))
    return round(0.8 * q + 0.2 * a, 4)


def score_demand(total_x=None, nii_x=None, retail_x=None):
    if total_x is None or nii_x is None or retail_x is None:
        return None
    r = RULES["market_demand"]
    total = interpolate(r["total_x"], total_x)
    nii = interpolate(r["nii_x"], nii_x)
    retail = interpolate(r["retail_x"], retail_x)
    return round(0.5 * total + 0.3 * nii + 0.2 * retail, 4)


def score_analyst(subscribe_count=None, analyst_count=None):
    if not analyst_count or subscribe_count is None:
        return None
    subscribe_ratio = max(0.0, min(1.0, float(subscribe_count) / float(analyst_count)))
    depth = interpolate(RULES["analyst_consensus"]["coverage_depth"], analyst_count)
    return round(0.8 * subscribe_ratio + 0.2 * depth, 4)


def score_environment(nifty_20d_return_pct=None, nifty_20d_vol_pct=None):
    if nifty_20d_return_pct is None or nifty_20d_vol_pct is None:
        return None
    r = RULES["sector_ipo_environment"]
    momentum = interpolate(r["nifty_20d_return_pct"], nifty_20d_return_pct)
    volatility = interpolate(r["nifty_20d_vol_pct"], nifty_20d_vol_pct)
    return round(0.7 * momentum + 0.3 * volatility, 4)


def score_gmp(gmp_pct=None):
    if gmp_pct is None:
        return None
    return round(interpolate(RULES["gmp_confirmation"]["gmp_pct"], gmp_pct), 4)
