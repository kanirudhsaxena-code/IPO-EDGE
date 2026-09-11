from __future__ import annotations

import json
from ipo_edge.db import connect

QUERY = r'''
WITH phase3 AS (
  SELECT i.ipo_id,a.classification,
    (c.evidence_delta_summary::jsonb -> 'component_scores' ->> 'institutional_conviction')::numeric AS inst,
    (c.evidence_delta_summary::jsonb -> 'component_scores' ->> 'market_demand')::numeric AS demand,
    (c.evidence_delta_summary::jsonb -> 'component_scores' ->> 'valuation')::numeric AS valuation
  FROM ipos i
  JOIN checkpoints c ON c.ipo_id=i.ipo_id AND c.checkpoint_type='T2_FINAL_DAY'
  JOIN assessments a ON a.ipo_id=i.ipo_id
  WHERE i.ipo_id>=8 AND i.issue_open_date BETWEEN DATE '2026-04-01' AND DATE '2026-06-30'
), pilot AS (
  SELECT i.ipo_id,a.classification,
    max(re.numeric_value) FILTER (WHERE re.research_block='R6_INSTITUTIONAL') AS inst,
    max(re.numeric_value) FILTER (WHERE re.research_block='R7_DEMAND') AS demand,
    max(re.numeric_value) FILTER (WHERE re.research_block='R3_VALUATION') AS valuation
  FROM ipos i
  JOIN assessments a ON a.ipo_id=i.ipo_id
  JOIN research_evidence re ON re.ipo_id=i.ipo_id
  WHERE i.ipo_id BETWEEN 2 AND 7
  GROUP BY i.ipo_id,a.classification
), b AS (SELECT * FROM phase3 UNION ALL SELECT * FROM pilot), rules AS (
 SELECT 'R6>=0.85 & R7>=0.80' rule, (inst>=.85 AND demand>=.80) hit,* FROM b UNION ALL
 SELECT 'R6>=0.85 & R7>=0.80 & R3>=0.75', (inst>=.85 AND demand>=.80 AND valuation>=.75),* FROM b
)
SELECT rule,
 count(*) FILTER (WHERE hit) AS selected,
 count(*) FILTER (WHERE hit AND classification='MISSED_OPPORTUNITY') AS winners,
 count(*) FILTER (WHERE hit AND classification='CORRECT_AVOIDANCE') AS non_winners,
 round((count(*) FILTER (WHERE hit AND classification='MISSED_OPPORTUNITY'))::numeric / nullif(count(*) FILTER (WHERE hit),0),4) AS precision,
 round((count(*) FILTER (WHERE hit AND classification='MISSED_OPPORTUNITY'))::numeric / 12,4) AS recall
FROM rules GROUP BY rule ORDER BY rule;
'''


def main():
    with connect() as conn:
        rows = conn.execute(QUERY).fetchall()
        learnings = conn.execute(
            "SELECT learning_id,hypothesis,development_result,status,proposed_change FROM learnings ORDER BY learning_id"
        ).fetchall()
    print(json.dumps({
        'development_rules': [
            {'rule': r[0], 'selected': r[1], 'winners': r[2], 'non_winners': r[3], 'precision': float(r[4]), 'recall': float(r[5])}
            for r in rows
        ],
        'learning_register': [
            {'learning_id': r[0], 'hypothesis': r[1], 'development_result': r[2], 'status': r[3], 'proposed_change': r[4]}
            for r in learnings
        ],
    }, indent=2, default=str))


if __name__ == '__main__':
    main()
