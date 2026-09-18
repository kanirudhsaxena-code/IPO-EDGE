"""Real PostgreSQL integration. Only an explicitly supplied disposable test DB."""
import json
import os
from datetime import datetime,timedelta,timezone
from pathlib import Path
import psycopg
import pytest
from psycopg.rows import dict_row
from ipo_edge.live_runtime import run, history
from ipo_edge.live_report import render
from ipo_edge.live_policy import IST
from ipo_edge.scoring import WEIGHTS

@pytest.fixture(scope='module')
def db():
    url=os.getenv('IPO_EDGE_DISPOSABLE_TEST_DSN')
    if not url: pytest.skip('Disposable PostgreSQL DSN not supplied')
    with psycopg.connect(url,autocommit=True) as c:
        if c.execute("SELECT to_regclass('public.checkpoints')").fetchone()[0]:
            raise RuntimeError('Integration suite requires an empty disposable database')
        for p in sorted(Path('db/migrations').glob('*.sql')):
            with c.transaction(): c.execute(p.read_text())
    return url

class FixtureWeb:
    def __init__(self,now):
        self.now=now
        today=now.astimezone(IST).date()
        self.items=[{'company_name':'TEST ACTIVE','segment':'MAINBOARD','issue_open_date':today,'issue_close_date':today+timedelta(days=2)},
                    {'company_name':'TEST LISTED','segment':'SME','issue_open_date':today-timedelta(days=5),'issue_close_date':today-timedelta(days=2),'listing_date':today}]
    def discover(self,now): return self.items,[],True
    def research(self,ipo,now):
        return {'research_complete':True,'scores':{k:1. for k in WEIGHTS},'evidence':[
            {'block':f'R{i}','source_url':'https://www.nseindia.com/test-fixture','retrieved_at':self.now.isoformat(),'verified':True,'values':{'fixture':True}}
            for i in range(1,9)]}
    def outcome(self,ipo,now):
        if ipo['company_name']!='TEST LISTED': return None
        return {'issue_price':100,'listing_price':90,'listing_gain_percent':-10,'listing_date':ipo['listing_date'],'source_url':'https://www.nseindia.com/test-fixture','crosscheck_url':'https://www.bseindia.com/test-fixture'}

def test_repeat_run_as_runtime_role_and_history_integrity(db):
    now=datetime.now(timezone.utc); web=FixtureWeb(now)
    config=json.loads(Path('config/framework_v1.1.json').read_text())
    with psycopg.connect(db,row_factory=dict_row) as c:
        for name,version in [('TEST HISTORICAL','1.0'),('TEST LISTED','1.1')]:
            item=web.items[1]
            i=c.execute('INSERT INTO ipos(company_name,segment,issue_open_date,issue_close_date) VALUES(%s,\'SME\',%s,%s) RETURNING ipo_id',(name,item['issue_open_date'],item['issue_close_date'])).fetchone()['ipo_id']
            c.execute("INSERT INTO checkpoints(ipo_id,checkpoint_type,checkpoint_time,grade,decision,framework_version) VALUES(%s,'T2_FINAL_DAY',%s,'A+','SUBSCRIBE',%s)",(i,now-timedelta(days=2),version))
        before=history(c); c.commit()
        c.execute('SET ROLE ipo_edge_runtime'); c.commit()
        first=run(c,web,config,now)
        second=run(c,web,config,now)
        assert first['status']=='COMPLETED',first
        assert second['status']=='COMPLETED',second
        assert first['checkpoints']==1 and second['checkpoints']==0
        assert first['outcomes']==1 and second['outcomes']==0
        assert c.execute('SELECT count(*) AS n FROM learnings').fetchone()['n']==1
        learning_runs=c.execute("SELECT status,recommendation_sample_size,independent_sample_size,notes FROM learning_runs ORDER BY learning_run_id").fetchall()
        assert len(learning_runs)>=2
        assert all(r['status'] in ('COMPLETED','DEFERRED') for r in learning_runs)
        assert all('automatic adoption disabled' in r['notes'] for r in learning_runs)
        assert history(c)==before
        report=render(c,second)
        assert len(report.split('\n\n'))==4
        assert 'Not Verified' in report
        c.commit()
        for sql in ('UPDATE checkpoints SET decision=decision','DELETE FROM checkpoints','TRUNCATE checkpoints CASCADE'):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with c.transaction(): c.execute(sql)
        assert history(c)==before

def test_discovery_failure_logged(db):
    class Broken:
        def discover(self,now): raise RuntimeError('Fixture discovery outage')
    with psycopg.connect(db,row_factory=dict_row) as c:
        c.execute('SET ROLE ipo_edge_runtime');c.commit()
        with pytest.raises(RuntimeError): run(c,Broken(),json.loads(Path('config/framework_v1.1.json').read_text()))
        assert c.execute('SELECT status FROM run_log ORDER BY run_id DESC LIMIT 1').fetchone()['status']=='FAILED'

def test_agent_intake_idempotent_and_rejects_future_evidence(db):
    now=datetime.now(timezone.utc); today=now.astimezone(IST).date()
    web=FixtureWeb(now); b=web.research({},now)
    with psycopg.connect(db,row_factory=dict_row) as c:
        c.execute('SET ROLE ipo_edge_runtime')
        i=c.execute("INSERT INTO ipos(company_name,segment,issue_open_date,issue_close_date) VALUES('TEST AGENT','MAINBOARD',%s,%s) RETURNING ipo_id",(today,today+timedelta(days=2))).fetchone()['ipo_id'];c.commit()
        result=c.execute('SELECT apply_ipo_edge_research(%s,%s::jsonb) AS result',(i,json.dumps(b))).fetchone()['result'];c.commit()
        assert result['status']=='RECORDED' and result['grade']=='A++'
        again=c.execute('SELECT apply_ipo_edge_research(%s,%s::jsonb) AS result',(i,json.dumps(b))).fetchone()['result'];c.commit()
        assert again['status']=='UNCHANGED'
        b['evidence'][0]['retrieved_at']=(now+timedelta(days=1)).isoformat()
        with pytest.raises(psycopg.errors.RaiseException):
            with c.transaction(): c.execute('SELECT apply_ipo_edge_research(%s,%s::jsonb)',(i,json.dumps(b)))
        obs=[{'issue_price':100,'listing_price':120,'listing_date':today.isoformat(),'verified':True,'retrieved_at':now.isoformat(),'source_url':u} for u in ('https://www.nseindia.com/test','https://www.bseindia.com/test')]
        i=c.execute("INSERT INTO ipos(company_name,segment,issue_open_date,issue_close_date) VALUES('TEST AGENT OUTCOME','MAINBOARD',%s,%s) RETURNING ipo_id",(today-timedelta(days=5),today-timedelta(days=2))).fetchone()['ipo_id'];c.commit()
        outcome=c.execute('SELECT apply_ipo_edge_outcome(%s,%s::jsonb) AS result',(i,json.dumps(obs))).fetchone()['result'];c.commit()
        assert outcome['status']=='RECORDED' and outcome['classification'] is None
        assert c.execute('SELECT apply_ipo_edge_outcome(%s,%s::jsonb) AS result',(i,json.dumps(obs))).fetchone()['result']['status']=='ALREADY_RECORDED';c.commit()
        assert c.execute('SELECT refresh_ipo_edge_metrics() AS result').fetchone()['result']['status']=='COMPLETED';c.commit()

def test_learning_evaluation_cannot_adopt_or_rewrite_rejected(db):
    with psycopg.connect(db,row_factory=dict_row) as c:
        i=c.execute("INSERT INTO learnings(hypothesis,observed_signal,status) VALUES('TEST EVALUATION','fixture','TESTING') RETURNING learning_id").fetchone()['learning_id'];c.commit()
        c.execute('SET ROLE ipo_edge_runtime');c.commit()
        ev={'status':'VALIDATED','development_result':'fixture development','validation_result':'fixture validation','evidence_query':'SELECT fixture','sample_adequacy':'fixture only','unseen_validation':True}
        r=c.execute('SELECT record_ipo_edge_learning_evaluation(%s,%s::jsonb) AS r',(i,json.dumps(ev))).fetchone()['r'];c.commit()
        assert r['status']=='VALIDATED' and r['production_changed'] is False
        ev['status']='ADOPTED'
        with pytest.raises(psycopg.errors.RaiseException):
            with c.transaction(): c.execute('SELECT record_ipo_edge_learning_evaluation(%s,%s::jsonb)',(i,json.dumps(ev)))
        ev['status']='REJECTED'
        c.execute('SELECT record_ipo_edge_learning_evaluation(%s,%s::jsonb)',(i,json.dumps(ev)));c.commit()
        ev['status']='TESTING'
        with pytest.raises(psycopg.errors.RaiseException):
            with c.transaction(): c.execute('SELECT record_ipo_edge_learning_evaluation(%s,%s::jsonb)',(i,json.dumps(ev)))

def test_cycle_gate_preserves_history_and_rejects_false_empty(db):
    now=datetime.now(timezone.utc);today=now.astimezone(IST).date().isoformat()
    with psycopg.connect(db,row_factory=dict_row) as c:
        before=history(c);c.commit()
        c.execute('SET ROLE ipo_edge_runtime');c.commit()
        def obs(group):
            return {'source_url':'https://'+group+'.example','ok':True,'enumerated':True,'pagination_complete':True,
                    'provenance_group':group,'independence_basis':'Independent fixture','retrieved_at':now.isoformat(),
                    'segments_searched':['MAINBOARD','SME'],'verified_empty':{'MAINBOARD':True,'SME':True},
                    'window_start':today,'window_end':today,'rows':[]}
        audit={'history_before':before,'observations':[obs('one'),obs('two')],'checks':[],'conflicts':[],
               'source_health':'DEGRADED','attempts':[{'provenance_group':g,'retrieved_at':now.isoformat()} for g in ('NSE','BSE','SEBI')]}
        rid=c.execute("INSERT INTO run_log(run_type,framework_version) VALUES('DISCOVERY','1.1') RETURNING run_id").fetchone()['run_id'];c.commit()
        result=c.execute('SELECT finalize_ipo_edge_cycle(%s,%s::jsonb) AS result',(rid,json.dumps(audit))).fetchone()['result'];c.commit()
        assert result['status']=='PARTIAL' and history(c)==before  # Known active ledger rows prevent false-empty success.
        c.execute("UPDATE ipos SET status='WITHDRAWN' WHERE company_name LIKE 'TEST %' AND issue_close_date>=CURRENT_DATE");c.commit()
        rid=c.execute("INSERT INTO run_log(run_type,framework_version) VALUES('DISCOVERY','1.1') RETURNING run_id").fetchone()['run_id'];c.commit()
        result=c.execute('SELECT finalize_ipo_edge_cycle(%s,%s::jsonb) AS result',(rid,json.dumps(audit))).fetchone()['result'];c.commit()
        assert result['status']=='COMPLETED' and history(c)==before
        audit['observations'][1]['segments_searched']=['MAINBOARD']
        rid=c.execute("INSERT INTO run_log(run_type,framework_version) VALUES('DISCOVERY','1.1') RETURNING run_id").fetchone()['run_id'];c.commit()
        result=c.execute('SELECT finalize_ipo_edge_cycle(%s,%s::jsonb) AS result',(rid,json.dumps(audit))).fetchone()['result'];c.commit()
        assert result['status']=='PARTIAL' and history(c)==before

def test_database_recovery_is_per_block_and_future_safe(db):
    now=datetime.now(timezone.utc)
    with psycopg.connect(db,row_factory=dict_row) as c:
        c.execute('SET ROLE ipo_edge_runtime');c.commit()
        bundle={'evidence':[],'attempts':[{'block':'R2','source_url':'https://'+g+'.example','retrieved_at':now.isoformat(),'provenance_group':g,'independence_basis':'Independent fixture','result':'Missing'} for g in ('one','two')]}
        with pytest.raises(psycopg.errors.RaiseException,match='R3'):
            with c.transaction():c.execute('SELECT validate_ipo_edge_recovery(%s::jsonb)',(json.dumps(bundle),))
        bundle['attempts']=[dict(a,block=b) for b in ('R2','R3','R4','R6','R7') for a in bundle['attempts']]
        c.execute('SELECT validate_ipo_edge_recovery(%s::jsonb)',(json.dumps(bundle),));c.commit()
        bundle['attempts'][-1]['retrieved_at']=(now+timedelta(days=1)).isoformat()
        with pytest.raises(psycopg.errors.RaiseException,match='R7'):
            with c.transaction():c.execute('SELECT validate_ipo_edge_recovery(%s::jsonb)',(json.dumps(bundle),))
