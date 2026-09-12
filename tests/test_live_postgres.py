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
