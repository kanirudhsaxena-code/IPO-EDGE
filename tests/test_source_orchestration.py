from copy import deepcopy
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
import requests
from ipo_edge.source_orchestration import SourceClient,reconcile,validate_recovery,validate_final,completion_gate,recover_block

NOW=datetime(2026,9,14,14,0,tzinfo=timezone.utc)
URL='https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx'

def response(code=200,text='ordinary public content',headers=None):
    return SimpleNamespace(status_code=code,text=text,content=text.encode(),headers=headers or {})

def observation(group,rows=None,segments=('MAINBOARD','SME')):
    return dict(source_url='https://'+group.lower()+'.example/calendar',ok=True,provenance_group=group,
                independence_basis='Independent original enumeration fixture',retrieved_at=NOW.isoformat(),
                window_start='2026-09-01',window_end='2026-09-30',enumerated=True,pagination_complete=True,
                segments_searched=list(segments),verified_empty={s:True for s in segments},rows=rows or [])

def row(segment='MAINBOARD'):
    return dict(company_name='Fixture '+segment,segment=segment,issue_open_date='2026-09-12',issue_close_date='2026-09-14')

def attempts(block):
    return [dict(block=block,source_url='https://'+g+'.example',provenance_group=g,independence_basis='Independent review',result='Missing',retrieved_at=NOW.isoformat()) for g in ('one','two')]

@pytest.mark.parametrize('failure',[requests.Timeout(),response(503),response(429,headers={'Retry-After':'1'})])
def test_bse_primary_transient_retry_recovers(failure):
    seq=iter([failure,response()]); delays=[]
    def fetch(*a,**k):
        x=next(seq)
        if isinstance(x,Exception): raise x
        return x
    c=SourceClient({},fetch,delays.append); r=c.fetch(URL)
    assert r.ok and len(r.attempts)==2 and r.attempts[-1]['final_source_status']=='SOURCE_RECOVERED'
    assert c.health=='DEGRADED' and delays==[1]

@pytest.mark.parametrize('response_value',[response(403),response(401),response(200,'verify you are human CAPTCHA')])
def test_access_restrictions_not_bypassed(response_value):
    calls=[]
    def fetch(*a,**k): calls.append(a);return response_value
    c=SourceClient({},fetch); assert not c.fetch(URL).ok
    assert not c.fetch('https://www.bseindia.com/corporates/ann.html').ok
    assert len(calls)==1 and c.attempts[-1]['error']=='ACCESS_RESTRICTED_COOLDOWN'

def test_long_retry_after_does_not_retry_early():
    calls=[]
    c=SourceClient({},lambda *a,**k: response(429,headers={'Retry-After':'120'}),calls.append)
    assert not c.fetch(URL).ok and not calls

@pytest.mark.parametrize('failed',[['BSE'],['NSE'],['BSE','NSE']])
def test_exchange_failures_allow_independent_reconciliation(failed):
    rows=[row(),row('SME')]
    observations=[dict(observation(g),ok=False) for g in failed]+[observation('ONE',rows),observation('TWO',rows)]
    assert reconcile(observations,NOW)['coverage_status']=='COVERAGE_COMPLETE'

def test_all_bse_routes_failure_and_alternate_official_success():
    c=SourceClient({},lambda u,**k: response(403) if 'bseindia' in u else response())
    assert not c.fetch(URL).ok
    r=c.fetch('https://www.bsesme.com/PublicIssues/SMEIPODRHP.aspx',fallback_from=URL)
    assert r.ok and r.attempts[0]['final_source_status']=='SOURCE_RECOVERED'
    assert c.health=='DEGRADED'

@pytest.mark.parametrize('segment',['MAINBOARD','SME'])
def test_one_segment_missing_prevents_complete(segment):
    obs=[observation(g,[row(segment)],(segment,)) for g in ('ONE','TWO')]
    assert reconcile(obs,NOW)['coverage_status']=='COVERAGE_PARTIAL'

def test_date_conflict_retained_and_affected_issue_withheld():
    a=row();b={**a,'issue_close_date':'2026-09-15'}
    r=reconcile([observation('ONE',[a]),observation('TWO',[b])],NOW)
    assert r['conflicts'] and r['coverage_status']=='COVERAGE_PARTIAL' and not r['rows']

def test_no_ipo_closes_requires_two_verified_empty_segments():
    r=reconcile([observation('ONE'),observation('TWO')],NOW)
    assert r['coverage_status']=='COVERAGE_COMPLETE' and r['rows']==[]
    assert completion_gate(r,[],[])=='COMPLETED'

@pytest.mark.parametrize('damage',['ok','pagination_complete','enumerated','verified_empty','segments_searched'])
def test_false_empty_and_truncated_pages_fail_closed(damage):
    a=observation('ONE');b=observation('TWO');b[damage]=False if damage in ('ok','enumerated','pagination_complete') else {} if damage=='verified_empty' else []
    assert reconcile([a,b],NOW)['coverage_status']=='COVERAGE_PARTIAL'

def test_syndicated_copies_are_not_independent():
    assert reconcile([observation('SAME'),observation('SAME')],NOW)['coverage_status']=='COVERAGE_PARTIAL'

def test_missing_critical_blocks_need_separate_attempts():
    bundle={'evidence':[],'attempts':attempts('R2')}
    with pytest.raises(ValueError,match='R3'):validate_recovery(bundle,NOW)
    bundle['attempts']=sum([attempts(b) for b in ('R2','R3','R4','R6','R7')],[])
    assert len(validate_recovery(bundle,NOW))==5
    bundle['attempts'][-1]['retrieved_at']=(NOW+timedelta(days=1)).isoformat()
    with pytest.raises(ValueError):validate_recovery(bundle,NOW)

def final_bundle():
    return {'subscription_is_final':True,'final_subscriptions':[dict(source_url='https://'+g+'.example/final',provenance_group=g,
        independence_basis='Independent final publication',retrieved_at=NOW.isoformat(),observed_at=NOW.isoformat(),verified=True,is_final=True,
        basis='entire issue; category multiples; final',total=20.,qib=30.,nii=40.,retail=10.) for g in ('one','two')]}

@pytest.mark.parametrize('field',['total','qib','nii','retail'])
def test_missing_or_conflicting_final_fields(field):
    b=final_bundle();del b['final_subscriptions'][0][field]
    with pytest.raises(ValueError):validate_final(b,NOW.date(),NOW)
    b=final_bundle();b['final_subscriptions'][1][field]+=1
    with pytest.raises(ValueError,match='CONFLICT'):validate_final(b,NOW.date(),NOW)

def test_recovered_final_day_t2_window_and_future_protection():
    b=final_bundle();assert validate_final(b,NOW.date(),NOW)
    for clock in (NOW-timedelta(hours=2),NOW+timedelta(days=1)):
        with pytest.raises(ValueError):validate_final(b,NOW.date(),clock)
    b['final_subscriptions'][0]['observed_at']=(NOW+timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError):validate_final(b,NOW.date(),NOW)

def test_official_final_source_does_not_require_new_framework_rule():
    b=final_bundle();b['final_subscriptions']=b['final_subscriptions'][:1]
    b['final_subscriptions'][0]['source_url']='https://www.nseindia.com/final'
    assert validate_final(b,NOW.date(),NOW)

def test_gate_cannot_omit_unresearched_ipo():
    d=reconcile([observation('ONE'),observation('TWO')],NOW)
    assert completion_gate(d,[],['missing'])=='PARTIAL'
    assert completion_gate(d,[dict(key='missing',checks_run=True,recovery_complete=True,disposition='CRITICAL_EVIDENCE_NV')],['missing'])=='COMPLETED'

def test_block_recovery_audit_survives_failure():
    c=SourceClient({},lambda *a,**k:response(403))
    candidate=dict(source_url=URL,provenance_group='BSE',independence_basis='Original exchange')
    r=recover_block(c,'R6',[candidate],lambda *a:None,NOW)
    assert r['status']=='CRITICAL_EVIDENCE_NV' and r['attempts'][0]['block']=='R6'


def test_full_september_month_and_unrelated_tables():
    from ipo_edge.live_sources import parse_named_calendar,parse_date
    html='<table><tr><th>Company IPO</th><th>Opening date</th><th>Closing Date</th><th>Type of IPO</th></tr><tr><td>Test</td><td>September 16, 2026</td><td>September 18, 2026</td><td>SME</td></tr></table>'
    rows=parse_named_calendar(html,'https://ipowatch.in/ipo-calendar-september-2026/')
    assert len(rows)==1 and rows[0]['issue_close_date'].isoformat()=='2026-09-18'
    assert parse_date('18 September 2026').isoformat()=='2026-09-18'
