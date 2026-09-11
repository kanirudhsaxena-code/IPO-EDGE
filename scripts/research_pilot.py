from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time, timezone
from pathlib import Path

from ipo_edge.adapters.ipoji import fetch_detail
from ipo_edge.adapters.ipoguru import fetch_consensus
from ipo_edge.adapters.market_env import fetch_nifty_environment
from ipo_edge.component_rules import (
    score_business, score_financial, score_valuation, score_institutional,
    score_demand, score_analyst, score_environment, score_gmp,
)
from ipo_edge.scoring import calculate_score
from ipo_edge.db import connect, insert_checkpoint

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/backtest/april_pilot_research.json"


def process_row(row):
    ipo_id, company_name, segment, opened, closed, issue_price = row
    cutoff = closed or opened
    try:
        ipoji = fetch_detail(company_name, evidence_cutoff=cutoff)
        analyst = fetch_consensus(company_name, evidence_cutoff=cutoff)
        environment = fetch_nifty_environment(cutoff)
    except Exception as exc:
        return {"ipo_id": ipo_id, "company_name": company_name, "segment": segment, "status": "FETCH_ERROR", "error": str(exc)[:300]}

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
    return {
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
    }


def add_evidence(conn, checkpoint_id, r, block, payload, source_url, source_name, verified, notes, published_at=None):
    conn.execute(
        """INSERT INTO research_evidence
           (ipo_id,checkpoint_id,research_block,field_name,value_text,source_url,source_name,published_at,retrieved_at,verification_status,notes)
           VALUES (%s,%s,%s,'phase3_reconstruction',%s,%s,%s,%s,now(),%s,%s)""",
        (r["ipo_id"], checkpoint_id, block, json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
         source_url, source_name, published_at, "VERIFIED" if verified else "NOT_VERIFIED", notes),
    )


def persist_result(conn, r):
    if r.get("status") == "FETCH_ERROR":
        return "FETCH_ERROR"
    existing = conn.execute(
        "SELECT checkpoint_id FROM checkpoints WHERE ipo_id=%s AND checkpoint_type='T2_FINAL_DAY' LIMIT 1",
        (r["ipo_id"],),
    ).fetchone()
    if existing:
        return "ALREADY_FROZEN"

    cutoff = datetime.fromisoformat(r["evidence_cutoff"]).date()
    cp = r["score_result"]
    checkpoint_id = insert_checkpoint(conn, r["ipo_id"], {
        "checkpoint_type": "T2_FINAL_DAY",
        "checkpoint_time": datetime.combine(cutoff, time(10, 0), tzinfo=timezone.utc),
        "score": cp["score"],
        "grade": cp["grade"],
        "decision": cp["decision"],
        "bear_gain_estimate": None,
        "base_gain_estimate": None,
        "bull_gain_estimate": None,
        "confidence": None,
        "hard_blocker": cp["hard_blocker"],
        "evidence_delta_summary": {
            "mode": "RETROSPECTIVE_T2_RECONSTRUCTION",
            "cutoff": r["evidence_cutoff"],
            "gates": r["critical_gate"],
            "component_scores": r["derived_scores"],
        },
        "framework_version": "1.0",
    })

    ip, an, env, gates, scores = r["ipoji"], r["analyst"], r["environment"], r["critical_gate"], r["derived_scores"]
    src = ip.get("source_url") or "https://www.ipoji.com/ipo-list?year=2026"
    add_evidence(conn, checkpoint_id, r, "R1_BUSINESS", {k:ip.get(k) for k in ("incorporation_year","company_age_years","latest_revenue_cr","profitable_period_ratio")}, src, "IPOJi", scores["business_quality"] is not None, f"Evidence cutoff {r['evidence_cutoff']}")
    add_evidence(conn, checkpoint_id, r, "R2_FINANCIALS", {k:ip.get(k) for k in ("roe_pct","roce_pct","debt_equity","ronw_pct")}, src, "IPOJi", gates["R2"], f"Evidence cutoff {r['evidence_cutoff']}")
    add_evidence(conn, checkpoint_id, r, "R3_VALUATION", {"pe_post":ip.get("pe_post")}, src, "IPOJi", gates["R3"], f"Evidence cutoff {r['evidence_cutoff']}")
    add_evidence(conn, checkpoint_id, r, "R4_PROMOTER_ISSUE", {"official_document_url":ip.get("official_document_url")}, ip.get("official_document_url") or src, "SEBI/NSE/BSE offer document", gates["R4"], "Strict official RHP/DRHP/prospectus gate")
    r5_ok = bool(an.get("historically_eligible") and an.get("analyst_count") is not None)
    add_evidence(conn, checkpoint_id, r, "R5_ANALYST", {k:an.get(k) for k in ("analyst_count","subscribe_count","avoid_count","published_at","historically_eligible")}, an.get("source_url") or "https://www.ipoguru.in/", "IPOGuru", r5_ok, "Analyst evidence admitted only when publication date <= T2", an.get("published_at"))
    add_evidence(conn, checkpoint_id, r, "R6_INSTITUTIONAL", {"qib_x":ip.get("qib_x")}, src, "IPOJi", gates["R6"], f"Final-day institutional evidence through {r['evidence_cutoff']}")
    add_evidence(conn, checkpoint_id, r, "R7_DEMAND", {k:ip.get(k) for k in ("total_x","nii_x","retail_x","gmp_pct","gmp_observed_date")}, src, "IPOJi", gates["R7"], "GMP is secondary and only dated observations <= T2 are admitted")
    add_evidence(conn, checkpoint_id, r, "R8_ENVIRONMENT", {k:env.get(k) for k in ("first_session","last_session","sessions","nifty_20d_return_pct","nifty_20d_vol_pct")}, env.get("source_url") or "https://query1.finance.yahoo.com/", "Yahoo Finance historical NIFTY", bool(env.get("found")), "Market data restricted to sessions on/before T2")
    conn.commit()
    return "FROZEN"


def main():
    with connect() as conn:
        rows = conn.execute(
            "SELECT ipo_id,company_name,segment,issue_open_date,issue_close_date,issue_price FROM ipos WHERE issue_open_date BETWEEN DATE '2026-04-01' AND DATE '2026-06-30' ORDER BY issue_open_date,company_name"
        ).fetchall()

    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(process_row, row): row for row in rows}
        for future in as_completed(futures):
            results.append(future.result())

    order = {row[0]: i for i, row in enumerate(rows)}
    results.sort(key=lambda r: order.get(r.get("ipo_id"), 10**9))

    fetch_errors = [r for r in results if r.get("status") == "FETCH_ERROR"]
    persistence = {"FROZEN": 0, "ALREADY_FROZEN": 0, "FETCH_ERROR": len(fetch_errors)}
    if not fetch_errors:
        with connect() as conn:
            for r in results:
                state = persist_result(conn, r)
                persistence[state] = persistence.get(state, 0) + 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(json.dumps({
        "cohort_count": len(results),
        "fetch_errors": len(fetch_errors),
        "ready": sum(r.get("status") == "READY_FOR_CHECKPOINT" for r in results),
        "nv": sum((r.get("score_result") or {}).get("grade") == "NV" for r in results),
        "grade_counts": {g: sum((r.get("score_result") or {}).get("grade") == g for r in results) for g in ("A++","A+","A","REJECT","NV")},
        "persistence": persistence,
    }, indent=2))
    if fetch_errors:
        raise SystemExit("Fetch errors present; nothing new persisted")


if __name__ == "__main__":
    main()
