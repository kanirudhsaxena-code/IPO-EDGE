from copy import deepcopy
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
import requests
from ipo_edge.source_orchestration import SourceClient,reconcile,validate_recovery,validate_final,completion_gate,recover_block
from ipo_edge.sources import verified_registrar_publication

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


def test_verified_dynamic_registrar_is_read_only_registered_source():
    registrar=verified_registrar_publication(
        'KFin Technologies Limited',
        'https://www.kfintech.com/',
        'INR000000221',
        'https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=10&regNo=INR000000221',
    )
    calls=[]
    def fetch(url,**kwargs):
        calls.append((url,kwargs))
        return response()
    client=SourceClient({},fetch,extra_publications=[registrar])
    result=client.fetch('https://www.kfintech.com/')
    assert result.ok
    assert result.attempts[0]['source_type']=='REGISTRAR'
    assert result.attempts[0]['authority']==3
    assert result.attempts[0]['provenance_group']=='REGISTRAR:INR000000221'
    assert calls and calls[0][1]['allow_redirects'] is False


def test_unverified_registrar_url_remains_blocked():
    client=SourceClient({},lambda *a,**k:response())
    with pytest.raises(ValueError,match='Unregistered'):
        client.fetch('https://registrar.example/')


def test_parser_completeness_counts_only_named_ipo_calendar_rows():
    from ipo_edge.live_sources import named_calendar_candidate_count, parse_named_calendar
    html = """
    <table><tr><th>Noise</th></tr><tr><td>Unrelated</td></tr></table>
    <table>
      <tr><th>Company IPO</th><th>Opening date</th><th>Closing Date</th><th>Type of IPO</th></tr>
      <tr><td>Alpha Limited</td><td>September 18, 2026</td><td>September 21, 2026</td><td>Mainboard</td></tr>
    </table>
    """
    rows=parse_named_calendar(html,'https://ipowatch.in/ipo-calendar-september-2026/')
    assert len(rows)==1
    assert named_calendar_candidate_count(html)==1


def test_reconciliation_aliases_same_issue_without_merging_unrelated_names():
    a=observation('ONE',[dict(company_name='National Stock Exchange of India Limited',segment='MAINBOARD',
        issue_open_date='2026-09-17',issue_close_date='2026-09-21')],('MAINBOARD',))
    b=observation('TWO',[dict(company_name='NSE',segment='MAINBOARD',
        issue_open_date='2026-09-17',issue_close_date='2026-09-21')],('MAINBOARD',))
    # SME must also be independently verified empty for the global gate.
    a['verified_empty']['SME']=True; b['verified_empty']['SME']=True
    a['segments_searched']=['MAINBOARD','SME']; b['segments_searched']=['MAINBOARD','SME']
    result=reconcile([a,b],NOW)
    assert result['segments']['MAINBOARD']['status']=='COVERAGE_COMPLETE'
    assert result['segments']['MAINBOARD']['ipo_count']==1


def test_closed_rows_do_not_block_current_discovery_coverage():
    closed=dict(company_name='Old Fixture',segment='MAINBOARD',
        issue_open_date='2026-09-01',issue_close_date='2026-09-03')
    active=row('MAINBOARD')
    a=observation('ONE',[closed,active],('MAINBOARD','SME'))
    b=observation('TWO',[active],('MAINBOARD','SME'))
    result=reconcile([a,b],NOW)
    assert result['segments']['MAINBOARD']['status']=='COVERAGE_COMPLETE'
    assert result['segments']['MAINBOARD']['coverage_scope']=='ACTIVE_OR_UPCOMING'
    assert result['segments']['MAINBOARD']['ipo_count']==1


def test_similar_names_on_different_issue_dates_remain_distinct():
    a=observation('ONE',[dict(company_name='Alpha India',segment='MAINBOARD',
        issue_open_date='2026-09-12',issue_close_date='2026-09-14')])
    b=observation('TWO',[dict(company_name='Alpha',segment='MAINBOARD',
        issue_open_date='2026-09-13',issue_close_date='2026-09-15')])
    result=reconcile([a,b],NOW)
    assert result['segments']['MAINBOARD']['status']=='COVERAGE_PARTIAL'


def test_ipo_markets_candidate_count_matches_valid_rows_only():
    from ipo_edge.live_sources import ipo_markets_candidate_count, parse_calendar
    html = """
    <table>
      <tr><th>Name</th><th>Status</th><th>Price</th><th>X</th><th>Y</th><th>Dates</th><th>Listing</th></tr>
      <tr><td><a href="/alpha">Alpha Mainboard IPO</a></td><td></td><td>100-110</td><td></td><td></td><td>18 Sep 2026 - 21 Sep 2026</td><td></td></tr>
      <tr><td><a href="/reit">Noise REIT</a></td><td></td><td>100</td><td></td><td></td><td>18 Sep 2026 - 21 Sep 2026</td><td></td></tr>
      <tr><td>Malformed SME IPO</td><td></td><td>100</td><td></td><td></td><td>18 Sep 2026 - 21 Sep 2026</td><td></td></tr>
    </table>
    """
    rows=parse_calendar(html,'https://ipomarkets.com/ipo-calendar/september-2026')
    assert len(rows)==1
    assert ipo_markets_candidate_count(html)==1


def test_partial_reconciliation_exposes_uncorroborated_active_issues():
    a=observation('ONE',[row('MAINBOARD')],('MAINBOARD','SME'))
    b=observation('TWO',[],('MAINBOARD','SME'))
    result=reconcile([a,b],NOW)
    missing=result['segments']['MAINBOARD']['uncorroborated']
    assert len(missing)==1
    assert missing[0]['company_name']=='Fixture MAINBOARD'
    assert missing[0]['groups']==['ONE']


def test_ipoji_index_parses_issue_dates_and_detail_url():
    from ipo_edge.live_sources import parse_ipoji_index, ipoji_index_candidate_count
    html="""
    <table>
      <tr><th>Company</th><th>Open Date</th><th>Close Date</th><th>Price</th><th>Listing Date</th></tr>
      <tr><td><a href="/ipo/alpha">Alpha Limited</a></td><td>18 Sep 2026</td><td>21 Sep 2026</td><td>100 - 110</td><td>25 Sep 2026</td></tr>
    </table>
    """
    rows=parse_ipoji_index(html,'https://www.ipoji.com/ipo-list?year=2026')
    assert ipoji_index_candidate_count(html)==1
    assert len(rows)==1
    assert rows[0]['company_name']=='Alpha Limited'
    assert rows[0]['issue_open_date'].isoformat()=='2026-09-18'
    assert rows[0]['issue_close_date'].isoformat()=='2026-09-21'
    assert rows[0]['detail_url']=='https://www.ipoji.com/ipo/alpha'
    assert rows[0]['segment'] is None


@pytest.mark.parametrize(('text','expected'),[
    ('Alpha SME IPO listed on NSE SME platform','SME'),
    ('Alpha Mainboard IPO details','MAINBOARD'),
    ('Alpha IPO details only',None),
    ('Alpha Mainboard and SME IPO',None),
])
def test_ipoji_segment_requires_explicit_unambiguous_label(text,expected):
    from ipo_edge.live_sources import parse_ipoji_segment
    assert parse_ipoji_segment('<html><body>'+text+'</body></html>')==expected


@pytest.mark.parametrize(('left','right'),[
    ('A-One Steels','A-One Steels India'),
    ('Jindal Supreme','Jindal Supreme India'),
    ('SpectraA Technology','SpectraA Technology Solutions'),
])
def test_safe_optional_suffix_aliases_merge_only_same_issue(left,right):
    a=observation('ONE',[dict(company_name=left,segment='MAINBOARD',
        issue_open_date='2026-09-17',issue_close_date='2026-09-21')],('MAINBOARD','SME'))
    b=observation('TWO',[dict(company_name=right,segment='MAINBOARD',
        issue_open_date='2026-09-17',issue_close_date='2026-09-21')],('MAINBOARD','SME'))
    a['verified_empty']['SME']=True
    b['verified_empty']['SME']=True
    result=reconcile([a,b],NOW)
    assert result['segments']['MAINBOARD']['status']=='COVERAGE_COMPLETE'
    assert result['segments']['MAINBOARD']['ipo_count']==1


def test_verified_detail_rows_can_corroborate_issue_without_certifying_universe():
    issue=row('MAINBOARD')
    complete_one=observation('ONE',[issue])
    complete_two=observation('TWO',[issue])
    # Keep two complete enumerators so universe completeness is independently certified.
    partial_detail=observation('IPOJI',[issue])
    partial_detail.update(ok=False,enumerated=False,issue_corroboration=True,verified_empty={})
    result=reconcile([complete_one,complete_two,partial_detail],NOW)
    assert result['coverage_status']=='COVERAGE_COMPLETE'
    assert 'IPOJI' not in result['segments']['MAINBOARD']['groups']

def test_partial_detail_source_cannot_replace_second_complete_enumerator():
    issue=row('MAINBOARD')
    complete_one=observation('ONE',[issue])
    partial_detail=observation('IPOJI',[issue])
    partial_detail.update(ok=False,enumerated=False,issue_corroboration=True,verified_empty={})
    result=reconcile([complete_one,partial_detail],NOW)
    assert result['segments']['MAINBOARD']['status']=='COVERAGE_PARTIAL'


def test_ipoji_segment_ignores_global_navigation_labels():
    from ipo_edge.live_sources import parse_ipoji_segment
    main='''<nav>Mainboard SME</nav><h1>Example IPO</h1><section><h2>Example IPO</h2><div>Mainboard</div></section>'''
    sme='''<nav>Mainboard SME</nav><h1>Example IPO</h1><section><h2>Example IPO</h2><div>SME</div></section>'''
    assert parse_ipoji_segment(main)=='MAINBOARD'
    assert parse_ipoji_segment(sme)=='SME'


def test_named_broker_calendar_accepts_explicit_two_digit_year_dates():
    from ipo_edge.live_sources import parse_named_calendar
    html='''<table>
      <tr><th>Company</th><th>Issue Type</th><th>Open Date</th><th>Close Date</th></tr>
      <tr><td>Example Ltd</td><td>Book Building - SME</td><td>23-Sep-26</td><td>25-Sep-26</td></tr>
    </table>'''
    rows=parse_named_calendar(html,'https://www.muthootsecurities.com/IPO/Forthcoming-Issues')
    assert len(rows)==1
    assert rows[0]['segment']=='SME'
    assert str(rows[0]['issue_open_date'])=='2026-09-23'
    assert str(rows[0]['issue_close_date'])=='2026-09-25'


def test_registered_broker_calendar_does_not_gain_universe_completeness_without_pagination_proof():
    issue=row('SME')
    one=observation('ONE',[issue],('SME',))
    broker=observation('CMOTS_BROKER_FEED',[issue],('SME',))
    broker['pagination_complete']=False
    result=reconcile([one,broker],NOW)
    assert result['segments']['SME']['status']=='COVERAGE_PARTIAL'
    assert 'CMOTS_BROKER_FEED' not in result['segments']['SME']['groups']


def test_corroborator_only_rows_do_not_expand_canonical_universe():
    canonical=row('SME')
    extra={**row('SME'),'company_name':'Single Source Extra'}
    one=observation('ONE',[canonical],('SME',))
    two=observation('TWO',[canonical],('SME',))
    detail=observation('DETAIL',[canonical,extra],('SME',))
    detail['enumerated']=False
    detail['pagination_complete']=False
    detail['issue_corroboration']=True
    result=reconcile([one,two,detail],NOW)
    names={r['company_name'] for r in result['rows']}
    assert canonical['company_name'] in names
    assert 'Single Source Extra' not in names
    assert result['segments']['SME']['status']=='COVERAGE_COMPLETE'


def test_iifl_upcoming_ipo_calendar_is_registered_as_guarded_broker_corroborator():
    from ipo_edge.sources import publication_for_url
    source=publication_for_url('https://www.indiainfoline.com/ipo/upcoming-ipo')
    assert source is not None
    assert source.group=='IIFL_CAPITAL'
    assert source.source_type=='BROKER_RESEARCH'
    assert source.calendar is True
