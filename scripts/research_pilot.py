from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ipo_edge.adapters.ipoji import fetch_detail
from ipo_edge.adapters.ipoguru import fetch_consensus
from ipo_edge.component_rules import (
    score_financial, score_valuation, score_institutional,
    score_demand, score_analyst, score_gmp,
)
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

        scores = {
            "financial_quality": score_financial(ipoji.get("roe_pct"), ipoji.get("roce_pct"), ipoji.get("debt_equity")),
            "valuation": score_valuation(ipoji.get("pe_post")),
            "institutional_conviction": score_institutional(ipoji.get("qib_x")),
            "market_demand": score_demand(ipoji.get("total_x"), ipoji.get("nii_x"), ipoji.get("retail_x")),
            "analyst_consensus": score_analyst(analyst.get("subscribe_count"), analyst.get("analyst_count")),
            "gmp_confirmation": score_gmp(ipoji.get("gmp_pct")),
            "business_quality": None,
            "sector_ipo_environment": None,
        }
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
            "derived_scores": scores,
            "status": "PARTIAL_EVIDENCE" if any(v is None for v in scores.values()) else "READY_FOR_CHECKPOINT",
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(json.dumps({"pilot_count": len(results), "ready": sum(r.get("status") == "READY_FOR_CHECKPOINT" for r in results)}, indent=2))


if __name__ == "__main__":
    main()
