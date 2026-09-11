from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from ipo_edge.adapters.ipoji import fetch_detail
from ipo_edge.db import connect
from ipo_edge.efficacy import OutcomeRecord, summarize
from ipo_edge.persistence import upsert_assessment, upsert_listing_outcome
from ipo_edge.pipeline import classify_outcome

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data/backtest/outcomes_discovery_only.json"
OUT = ROOT / "data/backtest/phase4_verified_outcomes.json"
TOLERANCE_PP = 0.75


def _listing_fields(raw_text: str):
    price = None
    date_iso = None
    m = re.search(r"List price\s+([0-9]+(?:\.[0-9]+)?)", raw_text, flags=re.I)
    if not m:
        m = re.search(r"Listing price\s+₹?\s*([0-9]+(?:\.[0-9]+)?)", raw_text, flags=re.I)
    if m:
        price = float(m.group(1))
    d = re.search(r"Listing date\s+(\d{1,2}\s+[A-Za-z]{3}\s+2026)", raw_text, flags=re.I)
    if d:
        date_iso = datetime.strptime(d.group(1), "%d %b %Y").date().isoformat()
    return price, date_iso


def _verify(row, ref_by_name):
    ipo_id, company_name, issue_price, checkpoint_id, grade, base_est = row
    try:
        detail = fetch_detail(company_name)
        listing_price, listing_date = _listing_fields(detail.get("raw_text", ""))
        if not listing_price or not listing_date or not issue_price:
            return {"ipo_id": ipo_id, "company_name": company_name, "status": "UNVERIFIED", "reason": "listing price/date/issue price missing"}
        gain = round((listing_price / float(issue_price) - 1.0) * 100.0, 2)
        ref = ref_by_name.get(company_name)
        if ref is None or ref.get("listing_gain_percent") is None:
            return {"ipo_id": ipo_id, "company_name": company_name, "status": "UNVERIFIED", "reason": "discovery cross-check missing", "ipoji_gain": gain}
        ref_gain = float(ref["listing_gain_percent"])
        delta = round(abs(gain - ref_gain), 2)
        if delta > TOLERANCE_PP:
            return {"ipo_id": ipo_id, "company_name": company_name, "status": "MISMATCH", "ipoji_gain": gain, "reference_gain": ref_gain, "delta_pp": delta, "source_url": detail.get("source_url")}
        return {
            "ipo_id": ipo_id, "company_name": company_name, "status": "VERIFIED",
            "issue_price": float(issue_price), "listing_price": listing_price, "listing_gain_percent": gain,
            "listing_date": listing_date, "source_url": detail.get("source_url"),
            "reference_gain": ref_gain, "crosscheck_delta_pp": delta,
            "checkpoint_id": checkpoint_id, "grade": grade,
            "base_estimate": float(base_est) if base_est is not None else None,
        }
    except Exception as exc:
        return {"ipo_id": ipo_id, "company_name": company_name, "status": "FETCH_ERROR", "reason": str(exc)[:300]}


def main():
    refs = json.loads(REF.read_text())
    ref_by_name = {r["company_name"]: r for r in refs}
    with connect() as conn:
        rows = conn.execute("""
            SELECT i.ipo_id,i.company_name,i.issue_price,c.checkpoint_id,c.grade,c.base_gain_estimate
            FROM ipos i JOIN checkpoints c ON c.ipo_id=i.ipo_id AND c.checkpoint_type='T2_FINAL_DAY'
            WHERE i.issue_open_date BETWEEN DATE '2026-04-01' AND DATE '2026-06-30'
            ORDER BY i.issue_open_date,i.company_name
        """).fetchall()
    if len(rows) != 56:
        raise RuntimeError(f"Phase 4 requires exactly 56 frozen development T2s, got {len(rows)}")

    verified = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_verify, r, ref_by_name) for r in rows]
        for f in as_completed(futures):
            verified.append(f.result())
    verified.sort(key=lambda x: int(x["ipo_id"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(verified, indent=2, ensure_ascii=False))

    bad = [r for r in verified if r["status"] != "VERIFIED"]
    if bad:
        print(json.dumps({"verified": len(verified)-len(bad), "blocked": len(bad), "blocked_rows": bad}, indent=2))
        raise RuntimeError("Phase 4 verification gate failed; no database outcomes persisted")

    records = []
    class_counts = {}
    with connect() as conn:
        for r in verified:
            outcome_id = upsert_listing_outcome(
                conn, r["ipo_id"], r["issue_price"], r["listing_price"], r["listing_gain_percent"], r["listing_date"], r["source_url"]
            )
            classification = classify_outcome(r["grade"], r["listing_gain_percent"])
            forecast_error = None if r["base_estimate"] is None else round(abs(r["listing_gain_percent"] - r["base_estimate"]), 2)
            missed_summary = "V1.0 final T2 was non-actionable despite >=20% actual listing gain; signal review deferred to learning phase." if classification == "MISSED_OPPORTUNITY" else None
            upsert_assessment(conn, r["ipo_id"], r["checkpoint_id"], outcome_id, classification, forecast_error, missed_summary)
            records.append(OutcomeRecord(grade=r["grade"], actual_gain=r["listing_gain_percent"], estimated_gain=r["base_estimate"]))
            class_counts[classification] = class_counts.get(classification, 0) + 1
        eff = summarize(records)
        conn.execute("""
            INSERT INTO efficacy_snapshots (
                as_of_date,framework_version,universe_count,recommendation_count,positive_hit_rate,twenty_percent_hit_rate,
                a_plus_plus_hit_rate,a_plus_hit_rate,opportunity_capture_rate,miss_rate,false_positive_rate,
                correct_avoidance_rate,avg_recommended_gain,avg_estimated_gain,forecast_error,upgrade_hit_rate,created_at
            ) VALUES (DATE '2026-07-02','1.0',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
        """, (
            len(records), eff.recommendation_count, eff.positive_hit_rate, eff.twenty_percent_hit_rate,
            eff.a_plus_plus_hit_rate, eff.a_plus_hit_rate, eff.opportunity_capture_rate, eff.miss_rate,
            eff.false_positive_rate, eff.correct_avoidance_rate, eff.avg_recommended_gain,
            eff.avg_estimated_gain, eff.forecast_error, eff.upgrade_hit_rate,
        ))
        conn.commit()

    print(json.dumps({
        "verified_outcomes": len(verified),
        "classification_counts": class_counts,
        "efficacy": eff.__dict__,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
