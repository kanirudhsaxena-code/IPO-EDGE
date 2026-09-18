"""Idempotent live orchestration; historical backtest scripts are never called."""
from __future__ import annotations
import json
from dataclasses import asdict
from datetime import datetime, timezone
from psycopg.rows import dict_row
from .db import insert_checkpoint, upsert_ipo
from .efficacy import OutcomeRecord, summarize
from .pipeline import classify_outcome
from .live_policy import IST, digest, decide, eligible_checkpoint, validate_release
from .source_orchestration import validate_final, completion_gate, identity

def receipt(conn, key, kind, run_id, payload, ipo_id=None):
    return conn.execute('INSERT INTO runtime_receipts(event_key,kind,ipo_id,run_id,payload) VALUES(%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING RETURNING event_key',
                        (key,kind,ipo_id,run_id,json.dumps(payload,default=str))).fetchone()

def history(conn):
    return conn.execute("SELECT count(*) AS count, md5(string_agg(to_jsonb(c)::text,E'\\n' ORDER BY checkpoint_id)) AS fingerprint FROM checkpoints c WHERE framework_version='1.0'").fetchone()

def assessment_rows(conn):
    return conn.execute("""SELECT i.ipo_id,i.company_name,c.checkpoint_id,c.framework_version,c.grade,c.base_gain_estimate,
      o.outcome_id,o.listing_gain_percent,
      EXISTS(SELECT 1 FROM checkpoints p WHERE p.ipo_id=c.ipo_id AND p.checkpoint_time<c.checkpoint_time AND p.grade NOT IN ('A+','A++')) AS upgraded
      FROM listing_outcomes o JOIN ipos i USING(ipo_id)
      JOIN LATERAL (SELECT * FROM checkpoints x WHERE x.ipo_id=i.ipo_id AND checkpoint_type='T2_FINAL_DAY'
       AND (checkpoint_time AT TIME ZONE 'Asia/Kolkata')::date<o.listing_date
       ORDER BY checkpoint_time DESC,checkpoint_id DESC LIMIT 1) c ON true""").fetchall()

def update_efficacy(conn, now):
    rows = assessment_rows(conn)
    for row in rows:
        # Original V1.0 assessment records remain as they were. Versioned summaries can be rebuilt.
        if row['framework_version'] != '1.1': continue
        gain = float(row['listing_gain_percent'])
        classification = classify_outcome(row['grade'],gain)
        conn.execute('''INSERT INTO assessments(ipo_id,canonical_checkpoint_id,outcome_id,classification,is_missed_opportunity,forecast_error_pp)
           VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(ipo_id) DO NOTHING''',
           (row['ipo_id'],row['checkpoint_id'],row['outcome_id'],classification,classification=='MISSED_OPPORTUNITY',
            None if row['base_gain_estimate'] is None else abs(gain-float(row['base_gain_estimate']))))
    summaries = []
    for version in sorted({r['framework_version'] for r in rows}):
        cohort = [r for r in rows if r['framework_version']==version]
        summary = asdict(summarize(OutcomeRecord(r['grade'],float(r['listing_gain_percent']),None if r['base_gain_estimate'] is None else float(r['base_gain_estimate']),r['upgraded']) for r in cohort))
        columns = list(summary)
        conn.execute(f"INSERT INTO efficacy_snapshots(as_of_date,framework_version,universe_count,{','.join(columns)}) VALUES(%s,%s,%s,{','.join(['%s']*len(columns))}) ON CONFLICT(as_of_date,framework_version) DO UPDATE SET universe_count=EXCLUDED.universe_count,"+','.join(f'{c}=EXCLUDED.{c}' for c in columns),
                     (now.astimezone(IST).date(),version,len(cohort),*[summary[c] for c in columns]))
        summaries.append({'version':version,'completed':len(cohort),**summary})
    return summaries, rows

def learn(conn, run_id, rows):
    v11_rows=[row for row in rows if row['framework_version']=='1.1']
    learning_status='COMPLETED' if v11_rows else 'DEFERRED'
    conn.execute(
        """INSERT INTO learning_runs
           (production_model_version,scope,status,recommendation_sample_size,
            independent_sample_size,completed_at,notes)
           VALUES('1.1','IPO_EDGE',%s,%s,%s,now(),%s)""",
        (
            learning_status,
            len(v11_rows),
            len(v11_rows),
            f'IPO EDGE autonomous learning governance cycle for runtime run {run_id}; automatic adoption disabled.',
        ),
    )
    for row in rows:
        if row['framework_version'] != '1.1': continue
        kind = classify_outcome(row['grade'],float(row['listing_gain_percent']))
        if kind not in ('MISSED_OPPORTUNITY','FALSE_POSITIVE'): continue
        key = f"learning:1.1:{row['checkpoint_id']}:{kind}"
        if receipt(conn,key,'LEARNING',run_id,{'classification':kind,'checkpoint_id':row['checkpoint_id']},row['ipo_id']):
            conn.execute("""INSERT INTO learnings(origin_ipo_id,hypothesis,observed_signal,status,proposed_change)
             VALUES(%s,%s,%s,'TESTING',%s)""",(row['ipo_id'],
             'Test whether pre-listing evidence coverage or institutional-demand calibration explains this '+kind,
             f"Frozen checkpoint {row['checkpoint_id']}; {kind}; actual gain {row['listing_gain_percent']}%",
             'Research contemporaneous signals, test on development and untouched validation cohorts, then propose a new version. No automatic adoption.'))
    # Measure adopted lane on live V1.1 cohorts only; append results without reclassifying old learnings.
    frozen = conn.execute("""SELECT c.evidence_delta_summary,o.listing_gain_percent FROM checkpoints c JOIN listing_outcomes o USING(ipo_id)
      WHERE c.framework_version='1.1' AND c.checkpoint_type='T2_FINAL_DAY'
      AND (c.checkpoint_time AT TIME ZONE 'Asia/Kolkata')::date<o.listing_date""").fetchall()
    selected = wins = winners = 0
    for row in frozen:
        data = json.loads(row['evidence_delta_summary'] or '{}')
        winner = float(row['listing_gain_percent'])>=20
        winners += winner
        if data.get('candidate'):
            selected += 1; wins += winner
    result = {'framework':'1.1','kind':'FORWARD_MONITORING','sample':len(frozen),'selected':selected,
              'precision':None if not selected else wins/selected,'recall':None if not winners else wins/winners,
              'status':'NO_FORWARD_OUTCOMES' if not frozen else 'OBSERVATION_ONLY', 'automatic_adoption':False}
    receipt(conn,'forward:'+digest(result),'VALIDATION',run_id,result)

def run(conn, provider, config, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None: raise ValueError('Timezone-aware run time required')
    conn.row_factory = dict_row
    # One run at a time across GitHub and manual callers; released even on exception.
    locked = conn.execute('SELECT pg_try_advisory_lock(741103) AS locked').fetchone()['locked']
    conn.commit()
    if not locked: return {'status':'SKIPPED_CONCURRENT_RUN'}
    run_id = None
    try:
        baseline = history(conn)
        execution=getattr(provider,'execution_config',None)
        if execution and (baseline['count']!=execution['historical_count'] or baseline['fingerprint']!=execution['historical_fingerprint']):
            raise RuntimeError('Locked historical baseline mismatch before writes')
        row = conn.execute("SELECT * FROM framework_versions WHERE version='1.1'").fetchone()
        if not row: raise RuntimeError('V1.1 not registered')
        validate_release(row,config)
        if now < row['effective_at']: raise RuntimeError('Cannot run V1.1 before release')
        run_id = conn.execute("INSERT INTO run_log(run_type,framework_version) VALUES('MANUAL','1.1') RETURNING run_id").fetchone()['run_id']
        conn.commit()
        errors = []
        research_results=[]; expected_keys=[]
        discovered, attempts, complete = provider.discover(now)
        known=conn.execute("SELECT company_name FROM ipos WHERE issue_close_date>=%s AND issue_open_date<=%s AND status NOT IN ('WITHDRAWN','CANCELLED')",(now.astimezone(IST).date(),now.astimezone(IST).date())).fetchall()
        missing_known={identity(r['company_name']) for r in known}-{identity(r['company_name']) for r in discovered}
        if missing_known:
            complete=False; errors.append('KNOWN_ACTIVE_IPOS_OMITTED:'+','.join(sorted(missing_known)))
        receipt(conn,'discovery:'+str(run_id),'DISCOVERY',run_id,{'attempts':attempts,'coverage_verified':complete,'count':len(discovered),'reconciliation':getattr(provider,'discovery_report',{})})
        conn.commit()
        if not complete: errors.append('UNIVERSE_COMPLETENESS_NOT_VERIFIED')
        checkpoint_count = researched = outcomes = 0
        for item in discovered:
            try:
                with conn.transaction():
                    matches = conn.execute('SELECT * FROM ipos WHERE lower(company_name)=lower(%s) AND issue_open_date=%s', (item['company_name'],item['issue_open_date'])).fetchall()
                    if len(matches)>1: raise ValueError('AMBIGUOUS_IPO_IDENTITY')
                    if matches:
                        ipo_id = matches[0]['ipo_id']
                        if matches[0]['segment'] != item['segment']: raise ValueError('SEGMENT_CONFLICT')
                        # Avoid rewriting historical identity or lifecycle state from an index page.
                    else:
                        ipo_id = conn.execute('''INSERT INTO ipos(company_name,segment,issue_open_date,issue_close_date,price_band_low,price_band_high,listing_date,status)
                          VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING ipo_id''',
                          (item['company_name'],item['segment'],item['issue_open_date'],item['issue_close_date'],item.get('price_band_low'),item.get('price_band_high'),item.get('listing_date'),
                           'UPCOMING' if item['issue_open_date']>now.astimezone(IST).date() else 'OPEN' if item['issue_close_date']>=now.astimezone(IST).date() else 'AWAITING_LISTING')).fetchone()['ipo_id']
                    previous = conn.execute('SELECT * FROM checkpoints WHERE ipo_id=%s ORDER BY checkpoint_time,checkpoint_id',(ipo_id,)).fetchall()
                    checkpoint_type = eligible_checkpoint(item,now,previous)
                    if checkpoint_type:
                        expected_keys.append(identity(item['company_name']))
                        # Research agent receipts supplement deterministic extraction using actual cited review.
                        agent = conn.execute("""SELECT payload FROM runtime_receipts WHERE kind='RESEARCH' AND ipo_id=%s
                         AND payload->>'provider'='research_agent' AND created_at<=%s AND (created_at AT TIME ZONE 'Asia/Kolkata')::date=%s
                         ORDER BY created_at DESC LIMIT 1""",(ipo_id,now,now.astimezone(IST).date())).fetchone()
                        bundle = agent['payload']['bundle'] if agent else provider.research(item,datetime.now(timezone.utc))
                        decision_time = datetime.now(timezone.utc)
                        checkpoint_type = eligible_checkpoint(item,decision_time,previous)
                        if checkpoint_type is None:
                            errors.append(f'CHECKPOINT_WINDOW_CLOSED:{ipo_id}')
                            continue
                        # Persist evidence before validation so rejected bundles remain auditable.
                        receipt(conn,f'research:{run_id}:{ipo_id}','RESEARCH',run_id,{'provider':'runtime','bundle':bundle},ipo_id)
                        decision = decide(bundle,decision_time)
                        researched += 1
                        if checkpoint_type=='T2_FINAL_DAY':
                            try: validate_final(bundle,item['issue_close_date'],decision_time)
                            except (ValueError,KeyError,TypeError) as exc:
                                errors.append(f'FINAL_SUBSCRIPTION_NOT_VERIFIED:{ipo_id}:{exc}')
                                receipt(conn,f'final-failure:{run_id}:{ipo_id}','RESEARCH',run_id,{'status':'CRITICAL_EVIDENCE_NV','reason':str(exc),'bundle':bundle},ipo_id)
                                continue
                        if not bundle.get('research_complete'):
                            errors.append(f'RESEARCH_REVIEW_PENDING:{ipo_id}')
                            # Never freeze a final-day grade using just numeric scraping.
                            if checkpoint_type=='T2_FINAL_DAY': continue
                        research_results.append({'key':identity(item['company_name']),'checks_run':bool(bundle.get('research_complete')),'recovery_complete':bool(bundle.get('research_complete')),'disposition':'CRITICAL_EVIDENCE_NV' if decision['grade']=='NV' else 'VERIFIED'})
                        fingerprint = digest({'decision':decision,'values':[e.get('values') for e in bundle['evidence']]})
                        same = previous and json.loads(previous[-1]['evidence_delta_summary'] or '{}').get('evidence_fingerprint')==fingerprint
                        if not same or checkpoint_type=='T2_FINAL_DAY':
                            cp = {'checkpoint_type':checkpoint_type,'checkpoint_time':decision_time,
                                  'score':decision['score'],'grade':decision['grade'],'decision':decision['decision'],
                                  'bear_gain_estimate':None,'base_gain_estimate':None,'bull_gain_estimate':None,'confidence':None,
                                  'hard_blocker':decision['hard_blocker'],'framework_version':'1.1',
                                  'evidence_delta_summary':{**decision,'evidence_fingerprint':fingerprint,'previous_grade':previous[-1]['grade'] if previous else None,
                                   'unresolved':bundle.get('unresolved',[]),'provider':bundle.get('provider_status')}}
                            # Existing helper returns a tuple; this runtime uses a dict-row cursor.
                            estimates=decision.get('estimates') or {}
                            cp_id = conn.execute('''INSERT INTO checkpoints(ipo_id,checkpoint_type,checkpoint_time,score,grade,decision,hard_blocker,evidence_delta_summary,framework_version,bear_gain_estimate,base_gain_estimate,bull_gain_estimate,confidence)
                             VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'1.1',%s,%s,%s,%s) RETURNING checkpoint_id''',
                             (ipo_id,cp['checkpoint_type'],cp['checkpoint_time'],cp['score'],cp['grade'],cp['decision'],cp['hard_blocker'],json.dumps(cp['evidence_delta_summary'],default=str),estimates.get('bear'),estimates.get('base'),estimates.get('bull'),None if not estimates else 100*estimates['confidence'])).fetchone()['checkpoint_id']
                            for e in bundle['evidence']:
                                if not e.get('source_url'): continue
                                block = {'R1':'R1_BUSINESS','R2':'R2_FINANCIALS','R3':'R3_VALUATION','R4':'R4_PROMOTER_ISSUE','R5':'R5_ANALYST','R6':'R6_INSTITUTIONAL','R7':'R7_DEMAND','R8':'R8_ENVIRONMENT'}[e['block']]
                                conn.execute('''INSERT INTO research_evidence(ipo_id,checkpoint_id,research_block,field_name,value_text,source_url,published_at,retrieved_at,verification_status)
                                  VALUES(%s,%s,%s,'live_review',%s,%s,%s,%s,%s)''',
                                  (ipo_id,cp_id,block,json.dumps(e,default=str),e['source_url'],e.get('published_at'),e['retrieved_at'],'VERIFIED' if e.get('verified') else 'NOT_VERIFIED'))
                            checkpoint_count += 1
                    if not conn.execute('SELECT 1 FROM listing_outcomes WHERE ipo_id=%s',(ipo_id,)).fetchone():
                        outcome = provider.outcome(item,now)
                        if outcome:
                            conn.execute('''INSERT INTO listing_outcomes(ipo_id,issue_price,listing_price,listing_gain_percent,listing_date,source_url)
                            VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(ipo_id) DO NOTHING''',(ipo_id,outcome['issue_price'],outcome['listing_price'],outcome['listing_gain_percent'],outcome['listing_date'],outcome['source_url']))
                            receipt(conn,f'outcome:{ipo_id}','OUTCOME',run_id,outcome,ipo_id); outcomes += 1
                conn.commit()
            except Exception as exc:
                conn.rollback()
                receipt(conn,'issue-failure:'+str(run_id)+':'+identity(item['company_name']),'RESEARCH',run_id,{'status':'CRITICAL_EVIDENCE_NV','reason':str(exc),'attempts':list(getattr(getattr(provider,'client',None),'attempts',[]))})
                conn.commit()
                errors.append(f"IPO_FAILED:{item['company_name']}:{type(exc).__name__}")
        summaries, assessed = update_efficacy(conn,now)
        learn(conn,run_id,assessed)
        if history(conn) != baseline: raise RuntimeError('Historical V1.0 integrity mismatch')
        receipt(conn,'integrity:'+str(run_id),'INTEGRITY',run_id,baseline)
        report=getattr(provider,'discovery_report',{})
        gated=completion_gate(report,research_results,expected_keys) if report else ('COMPLETED' if complete else 'PARTIAL')
        status = 'PARTIAL' if errors or gated!='COMPLETED' else 'COMPLETED'
        receipt(conn,'completion:'+str(run_id),'VALIDATION',run_id,{'coverage_status':report.get('coverage_status'),'source_health':report.get('source_health'),'checks':research_results,'status':status})
        conn.execute('''UPDATE run_log SET completed_at=now(),status=%s,errors=%s::jsonb,discovered_count=%s,researched_count=%s,checkpoint_count=%s,outcomes_added=%s WHERE run_id=%s''',
                     (status,json.dumps(errors),len(discovered),researched,checkpoint_count,outcomes,run_id))
        conn.commit()
        return {'run_id':run_id,'status':status,'errors':errors,'discovered':len(discovered),'researched':researched,'checkpoints':checkpoint_count,'outcomes':outcomes,'efficacy':summaries,'source_health':report.get('source_health','UNKNOWN'),'coverage_status':report.get('coverage_status','UNKNOWN')}
    except Exception as exc:
        conn.rollback()
        if run_id:
            receipt(conn,'failed-sources:'+str(run_id),'DISCOVERY',run_id,{'attempts':list(getattr(getattr(provider,'client',None),'attempts',[])),'status':'COVERAGE_PARTIAL'})
            conn.execute("UPDATE run_log SET status='FAILED',completed_at=now(),errors=%s::jsonb WHERE run_id=%s",(json.dumps([type(exc).__name__]),run_id)); conn.commit()
        raise
    finally:
        conn.execute('SELECT pg_advisory_unlock(741103)'); conn.commit()
