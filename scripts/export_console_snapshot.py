from __future__ import annotations
import json, os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

OUT=Path("runtime/console_snapshot.json")

def clean(v):
    if isinstance(v, Decimal): return float(v)
    if hasattr(v,"isoformat"): return v.isoformat()
    if isinstance(v, dict): return {k:clean(x) for k,x in v.items()}
    if isinstance(v, (list,tuple)): return [clean(x) for x in v]
    return v

def main():
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        issues=conn.execute("""
          select i.ipo_id,i.company_name,i.segment,i.exchange,i.issue_open_date,i.issue_close_date,i.listing_date,
                 i.price_band_low,i.price_band_high,i.status,
                 c.checkpoint_type,c.checkpoint_time,c.score,c.grade,c.decision,c.confidence,c.hard_blocker,c.evidence_delta_summary,
                 s.total_x,s.qib_x,s.nii_x,s.retail_x,
                 m.gmp_value,m.gmp_percent,m.gmp_direction
          from ipos i
          left join lateral(select * from checkpoints c where c.ipo_id=i.ipo_id order by c.checkpoint_time desc,c.checkpoint_id desc limit 1)c on true
          left join lateral(select * from subscription_snapshots s where s.ipo_id=i.ipo_id order by s.captured_at desc,s.snapshot_id desc limit 1)s on true
          left join lateral(select * from market_sentiment_snapshots m where m.ipo_id=i.ipo_id order by m.captured_at desc,m.snapshot_id desc limit 1)m on true
          where i.issue_close_date >= (now() at time zone 'Asia/Kolkata')::date - interval '2 days'
          order by i.issue_open_date asc nulls last,i.ipo_id desc limit 50
        """).fetchall()
        efficacy=conn.execute("select * from efficacy_snapshots order by created_at desc,efficacy_id desc limit 1").fetchone()
        counts=conn.execute("""select
          (select count(*) from ipos) ipos,
          (select count(*) from checkpoints) checkpoints,
          (select count(*) from research_evidence) evidence,
          (select count(*) from assessments) assessments,
          (select count(*) from listing_outcomes) listing_outcomes,
          (select count(*) from run_log) runs""").fetchone()
        latest_validated=conn.execute("""select i.company_name,i.segment,i.exchange,c.checkpoint_time,c.score,c.grade,c.decision
          from checkpoints c join ipos i using(ipo_id)
          where c.grade is not null and c.grade<>'NV'
          order by c.checkpoint_time desc,c.checkpoint_id desc limit 1""").fetchone()
        hist=conn.execute("""select
          count(*) assessed,
          count(*) filter(where a.classification='CORRECT_AVOIDANCE') correct_avoidance,
          count(*) filter(where a.classification='MISSED_OPPORTUNITY') missed_opportunity,
          avg(o.listing_gain_percent) all_outcomes_avg_listing_gain_pct,
          avg(o.listing_gain_percent) filter(where a.classification='CORRECT_AVOIDANCE') correct_avoidance_avg_listing_gain_pct,
          avg(o.listing_gain_percent) filter(where a.classification='MISSED_OPPORTUNITY') missed_opportunity_avg_listing_gain_pct
          from assessments a join listing_outcomes o using(outcome_id)""").fetchone()
        high=conn.execute("""select count(*) n,
          count(*) filter(where o.listing_gain_percent>0) positive,
          count(*) filter(where o.listing_gain_percent>=20) gain20,
          avg(o.listing_gain_percent) avg_gain
          from assessments a join checkpoints c on c.checkpoint_id=a.canonical_checkpoint_id join listing_outcomes o using(outcome_id)
          where c.grade='A' and c.decision='TRACK'""").fetchone()
        actionable=conn.execute("""select count(*) n from assessments a join checkpoints c on c.checkpoint_id=a.canonical_checkpoint_id
          where c.decision in ('APPLY','SUBSCRIBE','BUY')""").fetchone()
        h=dict(hist or {}); assessed=int(h.get("assessed") or 0); correct=int(h.get("correct_avoidance") or 0); missed=int(h.get("missed_opportunity") or 0)
        historical={
          "assessed":assessed,"correct_avoidance":correct,"missed_opportunity":missed,
          "decision_accuracy_pct":round(100*correct/assessed,2) if assessed else None,
          "miss_rate_pct":round(100*missed/assessed,2) if assessed else None,
          "all_outcomes_avg_listing_gain_pct":h.get("all_outcomes_avg_listing_gain_pct"),
          "correct_avoidance_avg_listing_gain_pct":h.get("correct_avoidance_avg_listing_gain_pct"),
          "missed_opportunity_avg_listing_gain_pct":h.get("missed_opportunity_avg_listing_gain_pct"),
          "high_grade_track_count":int((high or {}).get("n") or 0),
          "high_grade_positive_count":int((high or {}).get("positive") or 0),
          "high_grade_20pct_count":int((high or {}).get("gain20") or 0),
          "high_grade_hit_rate_pct":round(100*int((high or {}).get("gain20") or 0)/int((high or {}).get("n") or 1),2) if int((high or {}).get("n") or 0) else None,
          "high_grade_avg_listing_gain_pct":(high or {}).get("avg_gain"),
          "actionable_recommendation_count":int((actionable or {}).get("n") or 0),
          "actionable_recommendation_accuracy_pct":None
        }
        payload={"captured_at":datetime.now(timezone.utc).isoformat(),"framework_version":"1.1","issues":issues,
                 "efficacy":efficacy,"counts":counts,"latest_validated":latest_validated,"historical_efficacy":historical}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(clean(payload),indent=2,sort_keys=True)+"\n")

if __name__=="__main__": main()
