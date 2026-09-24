from __future__ import annotations

"""Read-only EH-01 forensic baseline for IPO EDGE V1.1.

This module never writes to the database and never recomputes model scores. It
classifies execution symptoms only; MODEL_RELATED_DEFERRED is a terminal tag,
not a proposal to change model policy.
"""

import json
import os
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

OUT = Path("runtime/execution_hardening_forensics.json")
CAUSES = {
    "RETRIEVAL",
    "IDENTITY",
    "TIMING",
    "CONFLICT",
    "UNIVERSE",
    "INFRASTRUCTURE",
    "MODEL_RELATED_DEFERRED",
    "UNRESOLVED",
}


def classify(row: dict) -> str:
    """Conservative execution-cause classifier using only persisted facts."""
    errors = " ".join(str(row.get(k) or "") for k in ("run_errors", "hard_blocker", "missed_signal_summary")).lower()
    if any(x in errors for x in ("duplicate", "alias", "identity", "name mismatch", "isin")):
        return "IDENTITY"
    if any(x in errors for x in ("late", "timing", "final day", "t2", "19:00", "closing")):
        return "TIMING"
    if any(x in errors for x in ("conflict", "disagree", "inconsistent")):
        return "CONFLICT"
    if any(x in errors for x in ("universe", "missing ipo", "not discovered", "discovery")):
        return "UNIVERSE"
    if any(x in errors for x in ("timeout", "401", "403", "captcha", "blocked", "network", "database", "exception")):
        return "INFRASTRUCTURE"
    if row.get("critical_missing", 0) or row.get("not_verified", 0):
        return "RETRIEVAL"
    if row.get("classification") == "MISSED_OPPORTUNITY" and row.get("grade") != "NV":
        return "MODEL_RELATED_DEFERRED"
    return "UNRESOLVED"


def collect(conn) -> dict:
    rows = conn.execute("""
      with latest_t2 as (
        select * from (
          select c.*, row_number() over(partition by c.ipo_id order by c.checkpoint_time desc,c.checkpoint_id desc) rn
          from checkpoints c where c.checkpoint_type='T2_FINAL_DAY'
        ) x where rn=1
      ), ev as (
        select ipo_id,
          count(*) filter(where verification_status='NOT_VERIFIED') not_verified,
          count(*) filter(where verification_status='CONFLICT') conflicts,
          count(distinct research_block) filter(where verification_status='VERIFIED') verified_blocks
        from research_evidence group by ipo_id
      ), last_run as (
        select errors from run_log order by started_at desc limit 1
      )
      select c.ipo_id,i.company_name,c.checkpoint_id,c.checkpoint_time,c.grade,c.decision,c.hard_blocker,
             a.classification,a.missed_signal_summary,
             coalesce(ev.not_verified,0) not_verified,coalesce(ev.conflicts,0) conflicts,
             greatest(0,5-coalesce((select count(distinct e.research_block) from research_evidence e
               where e.ipo_id=c.ipo_id and e.verification_status='VERIFIED'
               and e.research_block in ('R2_FINANCIALS','R3_VALUATION','R4_PROMOTER_ISSUE','R6_INSTITUTIONAL','R7_DEMAND')),0)) critical_missing,
             (select errors::text from last_run) run_errors
      from latest_t2 c join ipos i using(ipo_id)
      left join assessments a on a.canonical_checkpoint_id=c.checkpoint_id
      left join ev on ev.ipo_id=c.ipo_id
      order by c.ipo_id
    """).fetchall()
    records = []
    causes = Counter()
    for raw in rows:
        r = dict(raw)
        cause = classify(r)
        causes[cause] += 1
        records.append({**r, "execution_cause": cause})

    counts = conn.execute("""
      with t2 as (select distinct on (ipo_id) * from checkpoints where checkpoint_type='T2_FINAL_DAY' order by ipo_id,checkpoint_time desc,checkpoint_id desc)
      select
        (select count(*) from t2) frozen_t2,
        (select count(*) from assessments) assessed,
        (select count(*) from listing_outcomes) outcomes,
        (select count(*) from t2 left join assessments a on a.canonical_checkpoint_id=t2.checkpoint_id where a.assessment_id is null) t2_unassessed,
        (select count(*) from t2 where grade='NV') nv_t2,
        (select count(*) from run_log where status='PARTIAL') partial_runs,
        (select count(*) from run_log where status='FAILED') failed_runs
    """).fetchone()
    return {"framework_version": "1.1", "mode": "READ_ONLY_FORENSIC", "counts": dict(counts), "cause_counts": dict(sorted(causes.items())), "records": records}


def main() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        payload = collect(conn)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, default=str, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"counts": payload["counts"], "cause_counts": payload["cause_counts"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
