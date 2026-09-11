from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,time,timezone
from pathlib import Path
from ipo_edge.adapters.ipoji import fetch_detail
from ipo_edge.adapters.ipoguru import fetch_consensus
from ipo_edge.adapters.market_env import fetch_nifty_environment
from ipo_edge.component_rules import score_business,score_financial,score_valuation,score_institutional,score_demand,score_analyst,score_environment,score_gmp
from ipo_edge.scoring import calculate_score
from ipo_edge.db import connect,insert_checkpoint
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data/backtest/phase6_validation_t2.json'
def process_row(row):
 ipo_id,name,segment,opened,closed,issue_price=row; cutoff=closed or opened
 try: ip=fetch_detail(name,evidence_cutoff=cutoff); an=fetch_consensus(name,evidence_cutoff=cutoff); env=fetch_nifty_environment(cutoff)
 except Exception as e:return {'ipo_id':ipo_id,'company_name':name,'status':'FETCH_ERROR','error':str(e)[:300]}
 s={'business_quality':score_business(ip.get('company_age_years'),ip.get('latest_revenue_cr'),ip.get('profitable_period_ratio')),'financial_quality':score_financial(ip.get('roe_pct'),ip.get('roce_pct'),ip.get('debt_equity')),'valuation':score_valuation(ip.get('pe_post')),'institutional_conviction':score_institutional(ip.get('qib_x')),'market_demand':score_demand(ip.get('total_x'),ip.get('nii_x'),ip.get('retail_x')),'analyst_consensus':score_analyst(an.get('subscribe_count'),an.get('analyst_count')),'sector_ipo_environment':score_environment(env.get('nifty_20d_return_pct'),env.get('nifty_20d_vol_pct')),'gmp_confirmation':score_gmp(ip.get('gmp_pct'))}
 g={'R2':s['financial_quality'] is not None,'R3':s['valuation'] is not None,'R4':bool(ip.get('r4_document_verified')),'R6':s['institutional_conviction'] is not None,'R7':s['market_demand'] is not None}; z=calculate_score(s,critical_evidence_verified=all(g.values())); lane=s['institutional_conviction'] is not None and s['market_demand'] is not None and s['institutional_conviction']>=.85 and s['market_demand']>=.80
 return {'ipo_id':ipo_id,'company_name':name,'segment':segment,'issue_open_date':opened.isoformat(),'issue_close_date':closed.isoformat() if closed else None,'evidence_cutoff':cutoff.isoformat(),'issue_price':float(issue_price) if issue_price is not None else None,'retrieved_at':datetime.now(timezone.utc).isoformat(),'ipoji':{k:v for k,v in ip.items() if k!='raw_text'},'analyst':an,'environment':env,'derived_scores':s,'critical_gate':g,'score_result':{'score':z.score,'grade':z.grade,'decision':z.decision,'hard_blocker':z.hard_blocker},'learning_lane_r6_r7':lane,'status':'READY_FOR_CHECKPOINT' if z.score is not None else 'PARTIAL_EVIDENCE'}
def ev(conn,cp,r,b,p,u,n,v,note,pub=None):conn.execute("INSERT INTO research_evidence (ipo_id,checkpoint_id,research_block,field_name,value_text,source_url,source_name,published_at,retrieved_at,verification_status,notes) VALUES (%s,%s,%s,'phase6_validation',%s,%s,%s,%s,now(),%s,%s)",(r['ipo_id'],cp,b,json.dumps(p,default=str),u,n,pub,'VERIFIED' if v else 'NOT_VERIFIED',note))
def persist(conn,r):
 if conn.execute("SELECT 1 FROM checkpoints WHERE ipo_id=%s AND checkpoint_type='T2_FINAL_DAY'",(r['ipo_id'],)).fetchone():return 'ALREADY_FROZEN'
 d=datetime.fromisoformat(r['evidence_cutoff']).date(); q=r['score_result']; cp=insert_checkpoint(conn,r['ipo_id'],{'checkpoint_type':'T2_FINAL_DAY','checkpoint_time':datetime.combine(d,time(10),tzinfo=timezone.utc),'score':q['score'],'grade':q['grade'],'decision':q['decision'],'bear_gain_estimate':None,'base_gain_estimate':None,'bull_gain_estimate':None,'confidence':None,'hard_blocker':q['hard_blocker'],'evidence_delta_summary':{'mode':'VALIDATION_T2_BLIND','cutoff':r['evidence_cutoff'],'gates':r['critical_gate'],'component_scores':r['derived_scores'],'development_learning_test':{'r6_r7_lane':r['learning_lane_r6_r7']}},'framework_version':'1.0'})
 ip,an,en,g,s=r['ipoji'],r['analyst'],r['environment'],r['critical_gate'],r['derived_scores']; src=ip.get('source_url') or 'https://www.ipoji.com/'
 ev(conn,cp,r,'R1_BUSINESS',{k:ip.get(k) for k in ('incorporation_year','company_age_years','latest_revenue_cr','profitable_period_ratio')},src,'IPOJi',s['business_quality'] is not None,'Blind validation')
 ev(conn,cp,r,'R2_FINANCIALS',{k:ip.get(k) for k in ('roe_pct','roce_pct','debt_equity','ronw_pct')},src,'IPOJi',g['R2'],'Blind validation'); ev(conn,cp,r,'R3_VALUATION',{'pe_post':ip.get('pe_post')},src,'IPOJi',g['R3'],'Blind validation'); ev(conn,cp,r,'R4_PROMOTER_ISSUE',{'official_document_url':ip.get('official_document_url')},ip.get('official_document_url') or src,'Official offer document',g['R4'],'Strict R4 gate')
 r5=bool(an.get('historically_eligible') and an.get('analyst_count') is not None); ev(conn,cp,r,'R5_ANALYST',{k:an.get(k) for k in ('analyst_count','subscribe_count','avoid_count','published_at','historically_eligible')},an.get('source_url') or 'https://www.ipoguru.in/','IPOGuru',r5,'Publication <= T2',an.get('published_at'))
 ev(conn,cp,r,'R6_INSTITUTIONAL',{'qib_x':ip.get('qib_x')},src,'IPOJi',g['R6'],'Final-day'); ev(conn,cp,r,'R7_DEMAND',{k:ip.get(k) for k in ('total_x','nii_x','retail_x','gmp_pct','gmp_observed_date')},src,'IPOJi',g['R7'],'Final-day'); ev(conn,cp,r,'R8_ENVIRONMENT',{k:en.get(k) for k in ('first_session','last_session','sessions','nifty_20d_return_pct','nifty_20d_vol_pct')},en.get('source_url') or 'https://query1.finance.yahoo.com/','Yahoo Finance',bool(en.get('found')),'Sessions <= T2'); conn.commit(); return 'FROZEN'
def main():
 with connect() as c: rows=c.execute("SELECT ipo_id,company_name,segment,issue_open_date,issue_close_date,issue_price FROM ipos WHERE issue_open_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-10' ORDER BY issue_open_date,company_name").fetchall()
 if len(rows)!=67:raise RuntimeError(f'Expected 67, got {len(rows)}')
 out=[]
 with ThreadPoolExecutor(max_workers=6) as p:
  fs=[p.submit(process_row,r) for r in rows]
  for f in as_completed(fs):out.append(f.result())
 order={r[0]:i for i,r in enumerate(rows)};out.sort(key=lambda x:order.get(x.get('ipo_id'),9999));bad=[r for r in out if r.get('status')=='FETCH_ERROR'];OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2,default=str))
 if bad:raise RuntimeError(f'{len(bad)} fetch errors; nothing persisted')
 ps={}
 with connect() as c:
  for r in out: st=persist(c,r);ps[st]=ps.get(st,0)+1
 print(json.dumps({'count':len(out),'grades':{g:sum((r.get('score_result') or {}).get('grade')==g for r in out) for g in ('A++','A+','A','REJECT','NV')},'lane':sum(r['learning_lane_r6_r7'] for r in out),'persistence':ps},indent=2))
if __name__=='__main__':main()
