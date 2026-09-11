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


def main():
    results = []
    with connect() as conn:
        rows = conn.execute(
            "SELECT ipo_id,company_name,segment,issue_open_date,issue_close_date,issue_price FROM ipos WHERE issue_open_date BETWEEN DATE '2026-04-01' AND DATE '2026-06-30' ORDER BY issue_open_date,company_name"
        ).fetchall()

    for ipo_id, company_name, segment, opened, closed, issue_price in rows:
        cutoff = closed or opened
        try:
            ipoji = fetch_detail(company_name, evidence_cutoff=cutoff)
            analyst = fetch_consensus(company_name, evidence_cutoff=cutoff)
            environment = fetch_nifty_environment(cutoff)
        except Exception as exc:
            results.append({"ipo_id": ipo_id, "company_name": company_name, "segment": segment, "status": "FETCH_ERROR", "error": str(exc)[:300]})
            continue

        scores = {
            "business_quality": score_business(ipoji.get("company_age_years"), ipoji.get("latest_revenue_cr"), ipoji.get("profitable_period_ratio")),
            "financial_quality": score_financial(ipoji.get("roe_pct"), ipoji.get("roce_pct"), ipoji.get("debt_equity")),
            "valuation": score_valuation(ipoji.get("pe_post")),
            "institutional_conviction": score_institutional(ipoji.get("qib_x")),
            "market_demand": score_demand(ipoji.get("total_x"), ipoji.get("nii_x"), ipoji.get("retail_x")),
            "analyst_consensus": score_analyst(analyst.get("subscribe_count"), analyst.get("analyst_count")),
            "sector_ipo_environment": score_environment(environment.get("nifty_20d_return_pct"), environment.get("nifty_20d_vol_pct")),
            "gmp_confirmation": score_gmp(ipoji.get("gmp_pct")),
        }
        gates = {
            "R2": scores["financial_quality"] is not None,
            "R3": scores["valuation"] is not None,
            "R4": bool(ipoji.get("r4_document_verified")),
            "R6": scores["institutional_conviction"] is not None,
            "R7": scores["market_demand"] is not None,
        }
        scored = calculate_score(scores, critical_evidence_verified=all(gates.values()))
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
            "critical_gate": gates,
            "score_result": {"score": scored.score, "grade": scored.grade, "decision": scored.decision, "hard_blocker": scored.hard_blocker},
            "status": "READY_FOR_CHECKPOINT" if scored.score is not None else "PARTIAL_EVIDENCE",
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(json.dumps({
        "cohort_count": len(results),
        "fetch_errors": sum(r.get("status") == "FETCH_ERROR" for r in results),
        "ready": sum(r.get("status") == "READY_FOR_CHECKPOINT" for r in results),
        "nv": sum((r.get("score_result") or {}).get("grade") == "NV" for r in results),
        "grade_counts": {g: sum((r.get("score_result") or {}).get("grade") == g for r in results) for g in ("A++","A+","A","REJECT","NV")},
    }, indent=2))


if __name__ == "__main__":
    main()
