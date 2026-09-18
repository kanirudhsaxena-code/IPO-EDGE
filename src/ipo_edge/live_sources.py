"""Public-web discovery and evidence collection. Unsupported facts remain NV."""
from __future__ import annotations
import calendar
import io
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from . import component_rules as cr
from .live_policy import IST, digest
from .source_orchestration import SourceClient, reconcile, recover_block
from .sources import PUBLICATIONS, publication_for_url
import json
from pathlib import Path

UA = {'User-Agent':'Mozilla/5.0 (compatible; IPO-EDGE/1.1)'}
OFFICIAL = ('sebi.gov.in','nseindia.com','bseindia.com')

def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower().replace('limited','').replace('ltd','').replace('ipo',''))

def number(pattern, text):
    m = re.search(pattern, text, re.I)
    return float(m.group(1).replace(',', '')) if m else None

def parse_date(s):
    s = re.sub(r'\bSept\b', 'Sep', s)
    for fmt in ('%d %b %Y','%d %B %Y','%b %d, %Y'):
        try: return datetime.strptime(s, fmt).date()
        except ValueError: pass
    return None

def ipo_markets_candidate_count(html):
    """Count only structurally valid Mainboard/SME IPO rows for IPO Markets."""
    count=0
    for tr in BeautifulSoup(html,'html.parser').select('table tr'):
        cells=tr.find_all(['td','th'])
        if len(cells)<7:
            continue
        a=cells[0].find('a',href=True)
        if not a:
            continue
        values=[x.get_text(' ',strip=True) for x in cells]
        segment='SME' if 'SME' in values[0] else 'MAINBOARD' if 'Mainboard' in values[0] else None
        ds=re.findall(r'\d{1,2} [A-Za-z]+ 20\d{2}',values[5])
        if not segment or len(ds)!=2:
            continue
        opened,closed=map(parse_date,ds)
        name=a.get_text(' ',strip=True)
        if not opened or not closed or closed<opened:
            continue
        if any(x in name.lower() for x in ('reit','invit','investment trust')):
            continue
        count += 1
    return count


def named_calendar_candidate_count(html):
    """Count only rows from tables that structurally match the named IPO calendar schema."""
    count=0
    for table in BeautifulSoup(html,'html.parser').select('table'):
        trs=table.select('tr')
        if not trs:
            continue
        headers=[x.get_text(' ',strip=True).lower() for x in trs[0].select('th,td')]
        def col(pattern):
            return next((i for i,h in enumerate(headers) if re.search(pattern,h)),None)
        indexes=[col(p) for p in (
            r'ipo name|company|ipo$',
            r'open',
            r'clos',
            r'type|segment|platform',
        )]
        if any(x is None for x in indexes):
            continue
        maximum=max(indexes)
        for tr in trs[1:]:
            cells=tr.select('td,th')
            if len(cells)>maximum:
                count += 1
    return count


def parse_calendar(html, url):
    rows = []
    for tr in BeautifulSoup(html, 'html.parser').select('table tr'):
        cells = tr.find_all(['td','th'])
        if len(cells) < 7: continue
        a = cells[0].find('a', href=True)
        if not a: continue
        values = [c.get_text(' ', strip=True) for c in cells]
        segment = 'SME' if 'SME' in values[0] else 'MAINBOARD' if 'Mainboard' in values[0] else None
        ds = re.findall(r'\d{1,2} [A-Za-z]+ 20\d{2}', values[5])
        if not segment or len(ds) != 2: continue
        opened, closed = map(parse_date, ds)
        if not opened or not closed or closed < opened: continue
        name = a.get_text(' ', strip=True)
        if any(x in name.lower() for x in ('reit','invit','investment trust')): continue
        prices = re.findall(r'\d[\d,]*(?:\.\d+)?', values[2])
        lo, hi = (float(prices[0].replace(',','')), float(prices[-1].replace(',',''))) if prices else (None,None)
        listing_date = None
        match = re.search(r'Listed (\d{1,2} [A-Za-z]+)',values[1])
        if match: listing_date = parse_date(match[1]+' '+str(opened.year))
        rows.append({'company_name':name, 'segment':segment, 'issue_open_date':opened,
                     'issue_close_date':closed, 'price_band_low':lo, 'price_band_high':hi,
                     'listing_date':listing_date, 'discovery_url':url,
                     'detail_url':urljoin(url,a['href']),
                     'discovery_listing_price':number(r'₹\s*([\d,]+(?:\.\d+)?)',values[6]),
                     'discovery_issue_price':hi if listing_date else None})
    return rows

class PublicWeb:
    def __init__(self, execution_config=None):
        self.cache = {}
        self.execution_config = execution_config or json.loads(Path("config/source_execution_v1.1.json").read_text())
        self.client = SourceClient(self.execution_config)
        self.discovery_report = {}

    def fetch(self, url, attempts):
        result = self.client.fetch(url)
        attempts.extend(result.attempts)
        return result.text

    def discover(self, now):
        if not self.execution_config.get('enabled',True): return self.discover_legacy(now)
        observations=[]
        day=now.astimezone(IST).date()
        start=day.replace(day=1)-timedelta(days=1)
        end=(day.replace(day=28)+timedelta(days=4)).replace(day=1)
        months=sorted({(d.year,d.month) for d in (start,day,end)})
        for source in PUBLICATIONS[:8]:
            windows=months if '{month}' in source.url else [(day.year,day.month)]
            for year,month in windows:
                url=source.url.format(month=calendar.month_name[month].lower(),year=year)
                result=self.client.fetch(url, fallback_from=PUBLICATIONS[0].url if source.group!='BSE' or source!=PUBLICATIONS[0] else None)
                try:
                    rows=parse_calendar(result.text,url) if source.group=='IPOMARKETS' else parse_named_calendar(result.text,url)
                    soup=BeautifulSoup(result.text,'html.parser')
                    if source.group=='IPOMARKETS':
                        candidate_count=ipo_markets_candidate_count(result.text)
                    else:
                        candidate_count=named_calendar_candidate_count(result.text)
                    parse_complete=bool(rows) and candidate_count==len(rows)
                    if source.calendar and result.ok and not parse_complete:
                        self.client.attempts[-1].update(final_source_status='SOURCE_FAILED',error='PARSER_COVERAGE_UNVERIFIED',success=False)
                    text=soup.get_text(' ',strip=True)
                    segments=[seg for seg in ('MAINBOARD','SME') if re.search('mainboard|main board' if seg=='MAINBOARD' else r'\bSME\b',text,re.I)]
                    # Never infer completed pagination from the mere presence of some rows.
                    page_match=re.search(r'page\s+(\d+)\s+of\s+(\d+)',text,re.I)
                    pagination_ok=bool(page_match and page_match[1]==page_match[2]=='1')
                    # Specialist month pages are static single-page calendars only when no paging controls exist.
                    if source.group in ('IPOMARKETS','IPOWATCH'):
                        soup_page=BeautifulSoup(result.text,'html.parser')
                        explicit_next=bool(soup_page.select(
                            '[rel="next"], a[aria-label="Next"], button[aria-label="Next"]:not([disabled]), a.next, .next a'
                        ))
                        numbered_incomplete=bool(
                            page_match and int(page_match[1]) < int(page_match[2])
                        )
                        pagination_ok=not explicit_next and not numbered_incomplete
                    observations.append(dict(source_name=source.name,source_url=url,ok=result.ok,
                        retrieved_at=datetime.now(timezone.utc).isoformat(),provenance_group=source.group,
                        independence_basis='Separately published calendar; copied underlying observations must be excluded by research review',
                        enumerated=bool(source.calendar and parse_complete and result.ok),pagination_complete=pagination_ok,
                        segments_searched=segments,window_start=date(year,month,1).isoformat(),
                        window_end=date(year,month,calendar.monthrange(year,month)[1]).isoformat(),
                        verified_empty={},rows=rows))
                except Exception as exc:
                    self.client.attempts[-1].update(success=False,final_source_status='SOURCE_FAILED',error='PARSE_ERROR:'+type(exc).__name__)
                    observations.append({'source_url':url,'ok':False,'rows':[],'provenance_group':source.group})
        self.discovery_report=reconcile(observations,datetime.now(timezone.utc).astimezone(IST))
        self.discovery_report.update(observations=observations,attempts=list(self.client.attempts),source_health=self.client.health)
        return self.discovery_report['rows'],self.client.attempts,self.discovery_report['coverage_status']=='COVERAGE_COMPLETE'

    def discover_legacy(self, now):
        attempts, rows = [], []
        today = now.astimezone(IST).date()
        # Previous/current/next calendar months: covers recent listings and upcoming issues.
        months = {(d.year,d.month) for d in (today.replace(day=1)-timedelta(days=1),today,(today.replace(day=28)+timedelta(days=4)))}
        for year, month in sorted(months):
            url = f'https://ipomarkets.com/ipo-calendar/{calendar.month_name[month].lower()}-{year}'
            parsed = parse_calendar(self.fetch(url, attempts), url)
            if not parsed: attempts[-1] = {**attempts[-1], 'status':'EMPTY_OR_PARSE_FAILED'}
            rows.extend(parsed)
        # Independent reconciliation, with an explicit coverage warning on dynamic/unparseable pages.
        nse = 'https://www.nseindia.com/market-data/all-upcoming-issues-ipo'
        official = BeautifulSoup(self.fetch(nse, attempts), 'html.parser').get_text(' ',strip=True)
        coverage = bool(rows) and all(norm(r['company_name']) in norm(official) for r in rows if r['issue_close_date'] >= today)
        unique = {}
        for row in rows:
            key = (norm(row['company_name']),row['issue_open_date'])
            if key in unique and any(unique[key][k] != row[k] for k in ('segment','issue_close_date')):
                raise RuntimeError('Conflicting discovery identities')
            unique[key] = row
        if not unique: raise RuntimeError('Discovery returned no usable IPOs')
        return list(unique.values()), attempts, coverage

    def detail(self, name, now, attempts):
        index = self.fetch(f'https://www.ipoji.com/ipo-list?year={now.year}',attempts)
        links = [urljoin('https://www.ipoji.com',a['href']) for a in BeautifulSoup(index,'html.parser').select('a[href*="/ipo/"]') if norm(a.get_text(' ',strip=True)) == norm(name)]
        if not links: return '', None
        url = links[0]
        html = self.fetch(url,attempts)
        return html, url

    def research(self, ipo, now):
        attempts = []
        html, url = self.detail(ipo['company_name'], now, attempts)
        soup = BeautifulSoup(html, 'html.parser')
        # Official offer documents take precedence. A link alone is never verified R4 evidence.
        docs = []
        for a in soup.select('a[href]'):
            u = urljoin('https://www.ipoji.com',a['href']); host = urlparse(u).hostname or ''
            if any(host == d or host.endswith('.'+d) for d in OFFICIAL) and re.search(r'rhp|prospectus|offer.document',a.get_text(' ',strip=True)+' '+u,re.I):
                docs.append(u)
        for doc in sorted(set(docs))[:2]: self.fetch(doc,attempts)
        # Independent alternate-source recovery, recorded even when parsing fails.
        other = self.fetch(ipo['detail_url'],attempts) if ipo.get('detail_url') else ''
        text = soup.get_text(' ',strip=True)
        secondary = BeautifulSoup(other,'html.parser').get_text(' ',strip=True)
        patterns = {
          'qib':r'(?:Qualified Institutional Buyers\s*\(QIBs?\)|QIB)\s*([\d,.]+)\s*[x×]',
          'nii':r'(?:Non-Institutional Investors\s*\(NIIs?\)|NII)\s*([\d,.]+)\s*[x×]',
          'retail':r'(?:Retail|Individual)\s*([\d,.]+)\s*[x×]',
          'total':r'Total\s*([\d,.]+)\s*[x×]',
          'pe':r'P/E Post IPO[^0-9]*([\d,.]+)',
          'roe':r'ROE[^0-9]*([\d,.]+)\s*%',
          'roce':r'ROCE[^0-9]*([\d,.]+)\s*%',
          'de':r'Debt\s*/\s*Equity[^0-9]*([\d,.]+)'}
        vals = {k:number(p,text) for k,p in patterns.items()}
        conflicts = [k for k,p in patterns.items() if vals[k] is not None and number(p,secondary) is not None and abs(vals[k]-number(p,secondary)) > .02]
        for k in conflicts: vals[k] = None
        scores = {'financial_quality':cr.score_financial(vals['roe'],vals['roce'],vals['de']),
                  'valuation':cr.score_valuation(vals['pe']), 'institutional_conviction':cr.score_institutional(vals['qib']),
                  'market_demand':cr.score_demand(vals['total'],vals['nii'],vals['retail'])}
        evidence = []
        for block,key in [('R2','financial_quality'),('R3','valuation'),('R6','institutional_conviction'),('R7','market_demand')]:
            evidence.append({'block':block,'source_url':url,'retrieved_at':attempts[-1]['retrieved_at'],
                             'verified':bool(url and scores[key] is not None),'values':vals})
        evidence.append({'block':'R4','source_url':docs[0] if docs else url,
                         'retrieved_at':attempts[-1]['retrieved_at'],'verified':False,
                         'reason':'Governance, promoter and use-of-proceeds review is not established by a document link or numeric parser.'})
        # Numeric extraction cannot clear qualitative gaps. Still execute targeted recovery
        # and preserve evidence text references for the primary scheduled research agent.
        for block in ('R2','R3','R4','R6','R7'):
            if any(e['block']==block and e.get('verified') for e in evidence): continue
            candidates=[]
            for u in dict.fromkeys([*docs,ipo.get('detail_url'),url]):
                source=publication_for_url(u) if u else None
                if source:
                    candidates.append({'source_url':u,'provenance_group':source.group,
                        'independence_basis':'Separate publisher; factual independence requires qualitative review'})
            recovered=recover_block(self.client,block,candidates,lambda b,t,c: None,datetime.now(timezone.utc))
            attempts.extend(recovered['attempts'])
        return {'scores':scores,'evidence':evidence,'attempts':attempts,'conflicts':conflicts,
                'hard_blocker':'CONFLICTING_CRITICAL_EVIDENCE' if conflicts else None,
                'unresolved':['R1 qualitative business review','R4 governance review','R5 broker research','R8 market environment'],
                'provider_status':'PARTIAL_RESEARCH'}

    def outcome(self, ipo, now):
        if not ipo.get('listing_date') or ipo['listing_date'] > now.astimezone(IST).date(): return None
        attempts = []
        html,url = self.detail(ipo['company_name'],now,attempts)
        text = BeautifulSoup(html,'html.parser').get_text(' ',strip=True)
        price = number(r'(?:List|Listing) price\s*₹?\s*([\d,.]+)',text)
        d = re.search(r'Listing date\s*(\d{1,2} [A-Za-z]+ 20\d{2})',text,re.I)
        issue = number(r'(?:Issue Price|Offer Price)\s*₹?\s*([\d,]+(?:\.\d+)?)(?![\d,.]|\s*[–-])',text)
        # Only exact issue prices, not a price-band endpoint guessed before listing.
        expected = ipo.get('discovery_issue_price')
        if not price or not d or not issue or not expected or not ipo.get('discovery_listing_price'): return None
        if parse_date(d[1]) != ipo['listing_date'] or abs(price-ipo['discovery_listing_price']) > .02 or abs(issue-expected) > .02: return None
        return {'issue_price':issue,'listing_price':price,'listing_gain_percent':round((price/issue-1)*100,2),
                'listing_date':ipo['listing_date'],'source_url':url,'crosscheck_url':ipo['discovery_url'],'attempts':attempts}


def parse_named_calendar(html, url):
    result=[]
    for table in BeautifulSoup(html,'html.parser').select('table'):
        trs=table.select('tr')
        if not trs: continue
        headers=[x.get_text(' ',strip=True).lower() for x in trs[0].select('th,td')]
        def col(pattern):
            return next((i for i,h in enumerate(headers) if re.search(pattern,h)),None)
        name,opened,closed,segment=[col(p) for p in (r'ipo name|company|ipo$',r'open',r'clos',r'type|segment|platform')]
        if any(x is None for x in (name,opened,closed,segment)): continue
        for tr in trs[1:]:
            cells=tr.select('td,th')
            if len(cells)<=max(name,opened,closed,segment): continue
            values=[x.get_text(' ',strip=True) for x in cells]
            def dt(v):
                try:
                    from dateutil.parser import parse
                    if not re.search(r'20\d{2}',v): return None
                    return parse(re.sub(r'\bSept\b','Sep',v),dayfirst=True).date()
                except (ValueError,OverflowError): return None
            op,cl=dt(values[opened]),dt(values[closed])
            seg='SME' if 'sme' in values[segment].lower() else 'MAINBOARD' if 'main' in values[segment].lower() else None
            if not op or not cl or cl<op or not seg: continue
            a=cells[name].find('a',href=True)
            result.append(dict(company_name=values[name],segment=seg,issue_open_date=op,issue_close_date=cl,
                discovery_url=url,detail_url=urljoin(url,a['href']) if a else None,price_band_low=None,price_band_high=None,listing_date=None))
    return result
