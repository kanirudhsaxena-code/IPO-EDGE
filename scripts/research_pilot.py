from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ipo_edge.adapters.ipoji import fetch_detail
from ipo_edge.adapters.ipoguru import fetch_consensus
from ipo_edge.adapters.market_env import fetch_nifty_environment
from ipo_edge.component_rules import (
    score_business, score_financial, score_valuation, score_institutional,
    score_demand, score_analyst, score_environment, score_gmp,
)
from ipo_edge.scoring import calculate_score
from ipo_edge.db import connect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/backtest/april_pilot_research.json"
PILOT = [
    "Safety Controls & Devices",
    "Om Power Transmission",
    "Mehul Telecom",
    "Adisoft Tech",
    "Amba Auto",
    "OnEMI Technology Solutions",
]


def main():
    results = []
    with connect() as conn:
        db_rows = conn.execute(
            "SELECT ipo_id,company_name,segment,issue_open_date,issue_close_date,issue_price FROM ipos WHERE issue_open_date BETWEEN DATE '2026-04-01' AND DATE '2026-05-10' ORDER BY issue_open_date,company_name"
        ).fetchall()
    candidates = {r[1]: r for r in db_rows}

    for requested in PILOT:
        matched = None
        for name, row in candidates.items():
            if requested.lower() in name.lower() or name.lower() in requested.lower():
                matched = row
                break
        if not matched:
            results.append({"requested": requested, "status": "DB_MATCH_NOT_FOUND"})
            continue

        ipo_id, company_name, segment, opened, closed, issue_price = matched
        cutoff = closed or opened
        ipoji = fetch_detail(company_name, evidence_cutoff=cutoff)
        analyst = fetch_consensus(company_name)
        environment = fetch_nifty_environment(cutoff)

        scores = {
            "business_quality": score_business(
                ipoji.get("company_age_years"), ipoji.get("latest_revenue_cr"), ipoji.get("profitable_period_ratio")
            ),
            "financial_quality": score_financial(ipoji.get("roe_pct"), ipoji.get("roce_pct"), ipoji.get("debt_equity")),
            "valuation": score_valuation(ipoji.get("pe_post")),
            "institutional_conviction": score_institutional(ipoji.get("qib_x")),
            "market_demand": score_demand(ipoji.get("total_x"), ipoji.get("nii_x"), ipoji.get("retail_x")),
            "analyst_consensus": score_analyst(analyst.get("subscribe_count"), analyst.get("analyst_count")),
            "sector_ipo_environment": score_environment(
                environment.get("nifty_20d_return_pct"), environment.get("nifty_20d_vol_pct")
            ),
            "gmp_confirmation": score_gmp(ipoji.get("gmp_pct")),
        }
        critical_components_present = all(
            scores.get(k) is not None
            for k in ("financial_quality", "valuation", "institutional_conviction", "market_demand")
        )
        r4_verified = bool(ipoji.get("r4_document_verified"))
        critical_verified = critical_components_present and r4_verified
        scored = calculate_score(scores, critical_evidence_verified=critical_verified)

        results.append({
            "ipo_id": ipo_id,
            "company_name": company_name,
            "segment": segment,
            "issue_open_date": opened.isoformat(),
            "issue_close_date": closed.isoformat() if closed else None,
            "evidence_cutoff": cutoff.isoformat(),
            "issue_price": float(issue_price) if issue_price is not None else None,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "ipoji": {k:v for k,v in ipoji.items() if k != "raw_text"},
            "analyst": analyst,
            "environment": environment,
            "derived_scores": scores,
            "critical_gate": {
                "r2_financial": scores.get("financial_quality") is not None,
                "r3_valuation": scores.get("valuation") is not None,
                "r4_promoter_issue_document": r4_verified,
                "r6_institutional": scores.get("institutional_conviction") is not None,
                "r7_demand": scores.get("market_demand") is not None,
            },
            "score_result": {
                "score": scored.score,
                "grade": scored.grade,
                "decision": scored.decision,
                "hard_blocker": scored.hard_blocker,
            },
            "status": "READY_FOR_CHECKPOINT" if scored.score is not None else "PARTIAL_EVIDENCE",
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(json.dumps({
        "pilot_count": len(results),
        "ready": sum(r.get("status") == "READY_FOR_CHECKPOINT" for r in results),
        "grades": {r.get("company_name"): (r.get("score_result") or {}).get("grade") for r in results},
    }, indent=2))


if __name__ == "__main__":
    main()
