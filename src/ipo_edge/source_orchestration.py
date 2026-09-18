"""Execution resilience shared by the public provider and connector audit contract.
No grade calculation, framework mutation, credentials or browser workarounds.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse
import math
import re
import time
from difflib import SequenceMatcher
import requests
from .sources import publication_for_url

SEGMENTS = ('MAINBOARD', 'SME')
CRITICAL = ('R2', 'R3', 'R4', 'R6', 'R7')
FIELDS = ('total', 'qib', 'nii', 'retail')

def timestamp(value):
    d = datetime.fromisoformat(value)
    if d.tzinfo is None:
        raise ValueError('Timezone required')
    return d

def identity(name):
    return re.sub(r'[^a-z0-9]', '', re.sub(r'\b(limited|ltd|ipo)\b', '', name.lower()))

def _name_words(name):
    return [
        w for w in re.findall(r'[a-z0-9]+', str(name).lower())
        if w not in {'limited','ltd','ipo','of','the'}
    ]

def _acronym(name):
    words=[w for w in _name_words(name) if w!='india']
    return ''.join(w[0] for w in words if w)

def _same_company_name(a,b):
    ia,ib=identity(a),identity(b)
    if ia==ib:
        return True
    if _acronym(a) and _acronym(a)==identity(b):
        return True
    if _acronym(b) and _acronym(b)==identity(a):
        return True
    ratio=SequenceMatcher(None,ia,ib).ratio()
    return ratio>=0.82

def _reconciliation_key(row, union):
    direct=identity(row['company_name'])
    if direct in union:
        return direct
    for key,existing in union.items():
        same_issue=all(
            str(existing.get(field))==str(row.get(field))
            for field in ('segment','issue_open_date','issue_close_date')
        )
        if same_issue and _same_company_name(existing.get('company_name',''),row.get('company_name','')):
            return key
    return direct

def _observation_has_issue(observation, target):
    for row in observation.get('rows',[]):
        same_issue=all(
            str(target.get(field))==str(row.get(field))
            for field in ('segment','issue_open_date','issue_close_date')
        )
        if same_issue and _same_company_name(
            target.get('company_name',''), row.get('company_name','')
        ):
            return True
    return False

def independent_group(item):
    # Explicit lineage is required: different hosts alone do not prove independence.
    group = item.get('provenance_group')
    return group if isinstance(group, str) and group.strip() and item.get('independence_basis') else None

@dataclass
class FetchResult:
    text: str
    ok: bool
    attempts: list

class SourceClient:
    def __init__(self, config, transport=None, sleep=time.sleep, extra_publications=()):
        self.config = config
        self.transport = transport or requests.get
        self.sleep = sleep
        self.attempts = []
        self.blocked = set()
        self.extra_publications = tuple(extra_publications or ())

    def fetch(self, url, block=None, fallback_from=None):
        p = publication_for_url(url, self.extra_publications)
        if urlparse(url).scheme != 'https' or p is None:
            raise ValueError('Unregistered public source')
        start = len(self.attempts)
        host = urlparse(url).hostname
        for attempt in range(1, min(3, self.config.get('attempts_per_endpoint', 2))+1):
            row = dict(source_name=p.name, source_url=url, source_type=p.source_type,
                       authority=p.priority, retrieved_at=datetime.now(timezone.utc).isoformat(),
                       success=False, http_status=None, error=None, recovery_attempt=attempt,
                       fallback_source_used=url if fallback_from else None, fallback_from=fallback_from,
                       final_source_status='SOURCE_FAILED', block=block, provenance_group=p.group)
            retry = False; delay = 1
            try:
                if host in self.blocked:
                    row['error'] = 'ACCESS_RESTRICTED_COOLDOWN'
                    self.attempts.append(row)
                    return FetchResult('', False, self.attempts[start:])
                r = self.transport(url, timeout=self.config.get('timeout_seconds',20),
                                   headers={'User-Agent':'IPO-EDGE/1.1 public research'}, allow_redirects=False)
                row['http_status'] = r.status_code
                # Never follow an unvalidated redirect, change fingerprint or solve a challenge.
                if 300 <= r.status_code < 400:
                    row['error'] = 'REDIRECT_REQUIRES_REGISTERED_SURFACE'
                elif r.status_code in (401,403):
                    self.blocked.add(host); row['error'] = 'ACCESS_RESTRICTED'
                elif r.status_code == 429 or 500 <= r.status_code < 600:
                    row['error'] = 'RATE_LIMITED' if r.status_code == 429 else 'SERVER_ERROR'
                    retry = True
                    if r.status_code == 429:
                        try: delay = max(1, float(r.headers.get('Retry-After','1')))
                        except ValueError: retry = False
                        if delay > self.config.get('max_retry_delay_seconds',5): retry=False
                elif r.status_code != 200:
                    row['error'] = 'HTTP_ERROR'
                elif len(r.content)>self.config.get('max_response_bytes',20000000):
                    row['error'] = 'RESPONSE_TOO_LARGE'
                elif re.search(r'captcha|verify you are human|access denied|checking your browser',r.text,re.I):
                    row['error'] = 'ACCESS_CHALLENGE'; self.blocked.add(host)
                else:
                    row.update(success=True, final_source_status='SOURCE_RECOVERED' if attempt>1 or fallback_from else 'SOURCE_OK')
                    self.attempts.append(row)
                    if r.content.startswith(b'%PDF'):
                        import io
                        from pypdf import PdfReader
                        return FetchResult('\n'.join(x.extract_text() or '' for x in PdfReader(io.BytesIO(r.content)).pages),True,self.attempts[start:])
                    return FetchResult(r.text,True,self.attempts[start:])
            except (requests.Timeout, requests.ConnectionError) as exc:
                row['error']=type(exc).__name__; retry=True
            except Exception as exc:
                row['error']=type(exc).__name__; retry=False
            row.update(success=False,final_source_status='SOURCE_FAILED')
            self.attempts.append(row)
            if not retry or attempt >= min(3,self.config.get('attempts_per_endpoint',2)): break
            self.sleep(delay)
        return FetchResult('',False,self.attempts[start:])

    @property
    def health(self):
        return 'DEGRADED' if any(not a['success'] for a in self.attempts) else 'HEALTHY'

def reconcile(observations, now):
    """Union of independently enumerated segment calendars; missing != empty.
    Observations carry segments_searched, enumerated, pagination_complete,
    window_start/end, retrieved_at, rows and provenance. Filings are supplemental.
    """
    day = now.date().isoformat()
    usable=[]; conflicts=[]; union={}; provenance={}
    for obs in observations:
        if not obs.get('ok'): continue
        try:
            fresh = timestamp(obs['retrieved_at']).date()==now.date() and timestamp(obs['retrieved_at'])<=now
            fresh = fresh and obs['window_start']<=day<=obs['window_end']
        except (KeyError,ValueError,TypeError): fresh=False
        if not fresh: continue
        if obs.get('enumerated') and obs.get('pagination_complete') and independent_group(obs): usable.append(obs)
        for row in obs.get('rows',[]):
            key=_reconciliation_key(row,union)
            old=union.get(key)
            if old and any(str(old.get(k))!=str(row.get(k)) for k in ('segment','issue_open_date','issue_close_date')):
                conflicts.append({'company':key,'status':'SOURCE_CONFLICT','reason':'IDENTITY_OR_DATE_CONFLICT','sources':[provenance[key],obs.get('source_url')]})
            else: union[key]=row; provenance[key]=obs.get('source_url')
    status={}
    for segment in SEGMENTS:
        scans=[o for o in usable if segment in o.get('segments_searched',[])]
        groups={independent_group(o) for o in scans}
        expected={
            k for k,v in union.items()
            if v.get('segment')==segment and str(v.get('issue_close_date',''))>=day
        }
        corroborated=all(
            len({
                independent_group(o) for o in scans
                if _observation_has_issue(o,union[k])
            })>=2
            for k in expected
        )
        # Two enumerations may legitimately be empty only with explicit empty proof.
        empty_ok=bool(expected) or sum(bool(o.get('verified_empty',{}).get(segment)) for o in scans)>=2
        complete=len(groups)>=2 and corroborated and empty_ok and not conflicts
        status[segment]={'status':'COVERAGE_COMPLETE' if complete else 'COVERAGE_PARTIAL',
                         'groups':sorted(groups),'ipo_count':len(expected),'coverage_scope':'ACTIVE_OR_UPCOMING',
                         'source_urls':[o['source_url'] for o in scans]}
    blocked={c['company'] for c in conflicts}
    rows=[v for k,v in union.items() if k not in blocked]
    return {'segments':status,'conflicts':conflicts,'rows':rows,
            'coverage_status':'COVERAGE_COMPLETE' if all(s['status']=='COVERAGE_COMPLETE' for s in status.values()) else 'COVERAGE_PARTIAL'}

def validate_recovery(bundle, now):
    evidence=bundle.get('evidence',[])
    missing=[b for b in CRITICAL if not any(e.get('block')==b and e.get('verified') is True for e in evidence)]
    for block in missing:
        groups=set()
        for a in bundle.get('attempts',[]):
            try:
                valid=(a.get('block')==block and a.get('result') and a.get('source_url','').startswith('https://')
                       and timestamp(a['retrieved_at'])<=now)
            except (KeyError,ValueError,TypeError): valid=False
            if valid and independent_group(a): groups.add(independent_group(a))
        if len(groups)<2: raise ValueError('RECOVERY_INCOMPLETE:'+block)
    return missing

def validate_final(bundle, closing_day, now):
    from zoneinfo import ZoneInfo
    local=now.astimezone(ZoneInfo('Asia/Kolkata'))
    if local.date()!=closing_day or local.hour<19: raise ValueError('OUTSIDE_T2_WINDOW')
    if bundle.get('subscription_is_final') is not True: raise ValueError('FINAL_SUBSCRIPTION_NOT_VERIFIED')
    observations=bundle.get('final_subscriptions',[])
    groups=set(); reference=None; official=False
    for obs in observations:
        if obs.get('verified') is not True or obs.get('is_final') is not True or not obs.get('source_url','').startswith('https://'):
            raise ValueError('FINAL_SUBSCRIPTION_NOT_VERIFIED')
        if timestamp(obs['retrieved_at'])>now or timestamp(obs['observed_at'])>now or timestamp(obs['observed_at']).astimezone(ZoneInfo('Asia/Kolkata')).date()!=closing_day:
            raise ValueError('INVALID_FINAL_TIMESTAMP')
        if not obs.get('basis'): raise ValueError('FINAL_BASIS_REQUIRED')
        values=[obs.get(f) for f in FIELDS]
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in values):
            raise ValueError('MISSING_FINAL_FIELD')
        if reference and (reference['basis']!=obs['basis'] or any(abs(reference[f]-obs[f])>.02 for f in FIELDS)):
            raise ValueError('CONFLICTING_FINAL_SUBSCRIPTIONS')
        reference=obs
        p=publication_for_url(obs['source_url'])
        official=official or bool(p and p.source_type in ('EXCHANGE','OFFICIAL_REGULATORY'))
        group=independent_group(obs)
        if group: groups.add(group)
    if reference is None or (not official and len(groups)<2): raise ValueError('FINAL_CORROBORATION_REQUIRED')
    return True

def completion_gate(discovery, research_results, expected_keys):
    done={r['key'] for r in research_results if r.get('checks_run') and r.get('recovery_complete') and r.get('disposition') in ('VERIFIED','CRITICAL_EVIDENCE_NV')}
    passed=(discovery.get('coverage_status')=='COVERAGE_COMPLETE' and not discovery.get('conflicts') and set(expected_keys)<=done)
    return 'COMPLETED' if passed else 'PARTIAL'


def recover_block(client, block, candidates, verify, now):
    """Fetch permitted candidates for one missing block; verifier owns factual parsing.
    candidates contain URL, provenance_group and independence_basis. No value imputation.
    """
    attempts=[]; evidence=[]
    previous=None
    for candidate in candidates:
        fetched=client.fetch(candidate['source_url'],block=block,fallback_from=previous)
        for a in fetched.attempts:
            attempts.append({**a,'provenance_group':candidate.get('provenance_group'),
                             'independence_basis':candidate.get('independence_basis'),
                             'result':'FETCHED_FOR_BLOCK' if a['success'] else a['error']})
        previous=candidate['source_url']
        if fetched.ok:
            item=verify(block,fetched.text,candidate)
            if item:
                if item.get('block')!=block or timestamp(item['retrieved_at'])>now:
                    raise ValueError('Invalid recovered evidence')
                evidence.append(item)
    return {'block':block,'evidence':evidence,'attempts':attempts,
            'status':'SOURCE_RECOVERED' if any(e.get('verified') for e in evidence) else 'CRITICAL_EVIDENCE_NV'}
