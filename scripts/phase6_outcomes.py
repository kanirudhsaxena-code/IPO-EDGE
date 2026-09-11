from __future__ import annotations
import json,re,subprocess
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from ipo_edge.adapters.ipoji import fetch_detail
from ipo_edge.db import connect
from ipo_edge.persistence import upsert_listing_outcome,upsert_assessment
from ipo_edge.pipeline import classify_outcome
ROOT=Path(__file__).resolve().parents[1]; REF=ROOT/'data/backtest/outcomes_discovery_only.json'; OUT=ROOT/'data/backtest/phase6_verified_outcomes.json'; TOL=.75
DHOOT={'listing_price':1200.0,'listing_date':'2026-08-17','source_url':'https://www.business-standard.com/markets/news/dhoot-share-price-lists-at-38-premium-over-ipo-price-beats-expectations-126081700215_1.html'}

def fields(text):
 m=re.search(r'(?:List|Listing) price\s+₹?\s*([0-9]+(?:\.[0-9]+)?)',text,re.I); d=re.search(r'Listing date\s+(\d{1,2}\s+[A-Za-z]{3}\s+2026)',text,re.I)
 return (float(m.group(1)) if m else None,datetime.strptime(d.group(1),'%d %b %Y').date().isoformat() if d else None)
def verify(row,refs):
 ipo_id,name,issue,cp,grade,delta=row
 try:
  detail=fetch_detail(name); lp,ld=fields(detail.get('raw_text','')); src=detail.get('source_url')
  if name=='Dhoot Transmission': lp,ld,src=DHOOT['listing_price'],DHOOT['listing_date'],DHOOT['source_url']
  if not lp or not ld or not issue:return {'ipo_id':ipo_id,'company_name':name,'status':'PENDING_OR_UNVERIFIED','source_url':src}
  gain=round((lp/float(issue)-1)*100,2); ref=refs.get(name)
  if ref and ref.get('listing_gain_percent') is not None:
   rg=float(ref['listing_gain_percent']); diff=round(abs(gain-rg),2)
   if diff>TOL:return {'ipo_id':ipo_id,'company_name':name,'status':'MISMATCH','ipoji_gain':gain,'reference_gain':rg,'delta_pp':diff,'source_url':src}
  else: rg=None; diff=None
  lane=False
  try:
   obj=json.loads(delta) if isinstance(delta,str) else (delta or {}); lane=bool(obj.get('development_learning_test',{}).get('r6_r7_lane'))
  except Exception: pass
  return {'ipo_id':ipo_id,'company_name':name,'status':'VERIFIED','issue_price':float(issue),'listing_price':lp,'listing_gain_percent':gain,'listing_date':ld,'source_url':src,'reference_gain':rg,'crosscheck_delta_pp':diff,'checkpoint_id':cp,'grade':grade,'r6_r7_lane':lane}
 except Exception as e:return {'ipo_id':ipo_id,'company_name':name,'status':'FETCH_ERROR','reason':str(e)[:300]}
def main():
 subprocess.run(['python','scripts/build_universe.py'],check=True,cwd=ROOT); subprocess.run(['python','scripts/normalize_universe.py'],check=True,cwd=ROOT)
 refs={r['company_name']:r for r in json.loads(REF.read_text())}
 with connect() as c: rows=c.execute("SELECT i.ipo_id,i.company_name,i.issue_price,c.checkpoint_id,c.grade,c.evidence_delta_summary FROM ipos i JOIN checkpoints c ON c.ipo_id=i.ipo_id AND c.checkpoint_type='T2_FINAL_DAY' WHERE i.issue_open_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-10' ORDER BY i.issue_open_date,i.company_name").fetchall()
 if len(rows)!=67:raise RuntimeError(f'Expected 67 frozen validation T2s, got {len(rows)}')
 out=[]
 with ThreadPoolExecutor(max_workers=6) as p:
  fs=[p.submit(verify,r,refs) for r in rows]
  for f in as_completed(fs):out.append(f.result())
 out.sort(key=lambda x:int(x['ipo_id']));OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2,default=str))
 mism=[r for r in out if r['status']=='MISMATCH']; fetch=[r for r in out if r['status']=='FETCH_ERROR']; ver=[r for r in out if r['status']=='VERIFIED']; pending=[r for r in out if r['status']=='PENDING_OR_UNVERIFIED']
 if mism or fetch: print(json.dumps({'verified':len(ver),'pending':len(pending),'mismatch':mism,'fetch_errors':fetch},indent=2)); raise RuntimeError('Verification gate failed; no new T3 persisted')
 counts={}; lane_n=lane_win=0
 with connect() as c:
  for r in ver:
   oid=upsert_listing_outcome(c,r['ipo_id'],r['issue_price'],r['listing_price'],r['listing_gain_percent'],r['listing_date'],r['source_url']); cl=classify_outcome(r['grade'],r['listing_gain_percent']); upsert_assessment(c,r['ipo_id'],r['checkpoint_id'],oid,cl,None,'Validation miss under frozen V1.0.' if cl=='MISSED_OPPORTUNITY' else None); counts[cl]=counts.get(cl,0)+1
   if r['r6_r7_lane']: lane_n+=1; lane_win+=int(r['listing_gain_percent']>=20)
  c.commit()
 print(json.dumps({'verified_listed':len(ver),'pending_or_unverified':len(pending),'classification_counts':counts,'r6_r7_lane_listed':lane_n,'r6_r7_lane_winners20':lane_win,'r6_r7_precision':None if not lane_n else round(lane_win/lane_n,4),'pending_names':[r['company_name'] for r in pending]},indent=2))
if __name__=='__main__':main()
