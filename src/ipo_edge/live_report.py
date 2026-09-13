"""Four-table operational report; unknown estimates are never invented."""
from .live_runtime import assessment_rows

def cell(value):
    return 'Not Verified' if value is None else str(value).replace('|','\\|').replace('\n',' ')

def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',
                      *['| '+' | '.join(cell(v) for v in row)+' |' for row in rows]])

def render(conn, result):
    rates = lambda x: None if x is None else f'{100*x:.1f}%'
    efficacy = [[r['version'],r['completed'],r['recommendation_count'],rates(r['positive_hit_rate']),rates(r['twenty_percent_hit_rate']),rates(r['opportunity_capture_rate']),r['forecast_error']] for r in result.get('efficacy',[])]
    efficacy.append(['Run '+str(result.get('run_id')),result['status'],None,None,None,None,'; '.join(result.get('errors',[])) or 'Checks passed'])
    missed = [[r['company_name'],r['framework_version'],r['grade'],str(r['listing_gain_percent'])+'%','Review pre-listing evidence'] for r in assessment_rows(conn) if r['grade'] not in ('A+','A++') and r['listing_gain_percent']>=20]
    learning = conn.execute('SELECT learning_id,hypothesis,validation_result,status,adopted_framework_version FROM learnings ORDER BY learning_id').fetchall()
    current = conn.execute("""SELECT i.company_name,i.segment,i.issue_close_date,c.grade,c.decision,c.base_gain_estimate,c.evidence_delta_summary
      FROM ipos i LEFT JOIN LATERAL(SELECT * FROM checkpoints WHERE ipo_id=i.ipo_id ORDER BY checkpoint_time DESC,checkpoint_id DESC LIMIT 1)c ON true
      WHERE i.issue_close_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date ORDER BY i.issue_close_date,i.company_name""").fetchall()
    return '\n\n'.join([
      table(['Version/run','Completed/status','Recommendations','Positive hit','≥20% hit','Capture','Forecast error / run issues'],efficacy),
      table(['Missed IPO','Version','T2 grade','Listing gain','Assessment'],missed or [['None assessed',None,None,None,None]]),
      table(['Learning ID','Hypothesis','Validation','Status','Adopted version'],[list(r.values()) for r in learning]),
      table(['Current IPO','Segment','Closes','Grade','Estimated gain','Decision'],[[r['company_name'],r['segment'],r['issue_close_date'],r['grade'],r['base_gain_estimate'],r['decision']] for r in current])])+'\n'
