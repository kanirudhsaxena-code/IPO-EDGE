import json
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import pytest
from ipo_edge.live_policy import decide,eligible_checkpoint,validate_release
from ipo_edge.live_sources import parse_calendar
from ipo_edge.scoring import WEIGHTS

NOW=datetime(2026,9,14,14,0,tzinfo=timezone.utc)
def bundle():
    return {'research_complete':True,'scores':{k:1.0 for k in WEIGHTS},'evidence':[
        {'block':f'R{i}','source_url':'https://www.nseindia.com/test','retrieved_at':NOW.isoformat(),'verified':True} for i in range(1,9)]}

def test_no_retrospective_t2():
    ipo={'issue_close_date':date(2026,9,13)}
    assert eligible_checkpoint(ipo,NOW,[]) is None

def test_t2_only_on_close_day_after_cutoff():
    ipo={'issue_close_date':date(2026,9,14)}
    assert eligible_checkpoint(ipo,NOW,[])=='T2_FINAL_DAY'
    assert eligible_checkpoint(ipo,NOW-timedelta(hours=8),[])=='T1_DISCOVERY'
    assert eligible_checkpoint(ipo,NOW,[{'checkpoint_type':'T2_FINAL_DAY'}]) is None

def test_nv_never_promoted_by_overlay():
    b=bundle(); b['evidence'][3]['verified']=False
    d=decide(b,NOW)
    assert d['grade']=='NV' and not d['candidate'] and d['decision']=='NO_ACTION'

def test_overlay_does_not_change_grade():
    b=bundle(); b['scores']={k:0.0 for k in WEIGHTS}; b['scores'].update(institutional_conviction=.9,market_demand=.9)
    d=decide(b,NOW)
    assert d['candidate'] and d['grade']=='REJECT' and d['decision']=='REJECT'

def test_future_evidence_rejected():
    b=bundle(); b['evidence'][0]['retrieved_at']=(NOW+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError): decide(b,NOW)

def test_incomplete_claimed_review_rejected():
    b=bundle(); b['evidence'].pop()
    with pytest.raises(ValueError): decide(b,NOW)

def test_unknown_estimates_remain_unknown():
    assert decide(bundle(),NOW)['estimates'] is None

def test_september_calendar_and_band_not_issue_price():
    html='<table><tr><th><a href="/ipo/example">Example</a> Mainboard</th><td>Open</td><td>₹90–₹100</td><td>—</td><td>1×</td><td>14 Sept 2026 – 16 Sept 2026</td><td>—</td></tr></table>'
    r=parse_calendar(html,'https://ipomarkets.com/ipo-calendar/september-2026')[0]
    assert r['issue_close_date']==date(2026,9,16)
    assert r['price_band_high']==100 and r['discovery_issue_price'] is None

def test_release_mismatch_rejected():
    config=json.loads(Path('config/framework_v1.1.json').read_text())
    with pytest.raises(RuntimeError): validate_release({'version':'1.0','status':'FROZEN','scoring_config':WEIGHTS},config)
