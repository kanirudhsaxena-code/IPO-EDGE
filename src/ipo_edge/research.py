from collections import defaultdict
from statistics import mean
from .evidence import EvidenceItem, critical_evidence_verified

BLOCK_TO_COMPONENT = {
    "R1": "business_quality", "R2": "financial_quality", "R3": "valuation",
    "R4": "business_quality", "R5": "analyst_consensus",
    "R6": "institutional_conviction", "R7": "market_demand",
    "R8": "sector_ipo_environment",
}

COMPONENTS = [
    "business_quality", "financial_quality", "valuation",
    "institutional_conviction", "market_demand", "analyst_consensus",
    "sector_ipo_environment", "gmp_confirmation",
]


def _clamp(v):
    return max(0.0, min(1.0, float(v)))


def derive_component_scores(items):
    grouped = defaultdict(list)
    gmp = []
    for e in items:
        if e.verification_status != "VERIFIED" or e.numeric_value is None:
            continue
        if e.field_name == "gmp_percent":
            gmp.append(_clamp((float(e.numeric_value) + 10.0) / 50.0))
            continue
        key = BLOCK_TO_COMPONENT.get(e.block)
        if key:
            grouped[key].append(_clamp(e.numeric_value))
    result = {k: None for k in COMPONENTS}
    for key, vals in grouped.items():
        if vals:
            result[key] = round(mean(vals), 4)
    if gmp:
        result["gmp_confirmation"] = round(mean(gmp), 4)
    return result


def research_gate(items):
    if not critical_evidence_verified(items):
        return False, "CRITICAL_EVIDENCE_NOT_VERIFIED"
    scores = derive_component_scores(items)
    missing = [k for k, v in scores.items() if v is None]
    if missing:
        return False, "MISSING_COMPONENTS:" + ",".join(missing)
    return True, None
