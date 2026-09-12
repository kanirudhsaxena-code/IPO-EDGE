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

UA = {'User-Agent':'Mozilla/5.0 (compatible; IPO-EDGE/1.1)'}
OFFICIAL = ('sebi.gov.in','nseindia.com','bseindia.com')

def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower().replace('limited','').replace('ltd','').replace('ipo',''))

def number(pattern, text):
    m = re.search(pattern, text, re.I)
    return float(m.group(1).replace(',', '')) if m else None

def parse_date(s):
    s = s.replace('Sept', 'Sep')
    for fmt in ('%d %b %Y','%d %B %Y','%b %d, %Y'):
        try: return datetime.strptime(s, fmt).date()
        except ValueError: pass
    return None

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
    def __init__(self):
        self.cache = {}

    def fetch(self, url, attempts):
        host = urlparse(url).hostname or ''
        if urlparse(url).scheme != 'https' or not any(host == d or host.endswith('.'+d) for d in (*OFFICIAL,'ipoji.com','ipoguru.in','ipomarkets.com')):
            raise ValueError('Source outside configured public-source allowlist')
        if url in self.cache:
            value, receipt = self.cache[url]
            attempts.append(receipt)
            return value
        receipt = {'source_url':url, 'retrieved_at':datetime.now(timezone.utc).isoformat()}
        try:
            r = requests.get(url, headers=UA, timeout=20)
            r.raise_for_status()
            receipt['status'] = 'FETCHED'
            if len(r.content) > 20_000_000: raise ValueError('Source exceeds size limit')
            if r.content.startswith(b'%PDF'):
                from pypdf import PdfReader
                value = '\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(r.content)).pages)
            else: value = r.text
            receipt['sha256'] = digest(value)
        except Exception as exc:
            value = ''
            receipt.update(status='UNAVAILABLE', error=type(exc).__name__)
        self.cache[url] = (value, receipt)
        attempts.append(receipt)
        return value

    def discover(self, now):
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
        issue = number(r'(?:Issue Price|Offer Price)\s*₹?\s*([\d,.]+)(?!\s*[–-])',text)
        # Only exact issue prices, not a price-band endpoint guessed before listing.
        expected = ipo.get('discovery_issue_price')
        if not price or not d or not issue or not expected or not ipo.get('discovery_listing_price'): return None
        if parse_date(d[1]) != ipo['listing_date'] or abs(price-ipo['discovery_listing_price']) > .02 or abs(issue-expected) > .02: return None
        return {'issue_price':issue,'listing_price':price,'listing_gain_percent':round((price/issue-1)*100,2),
                'listing_date':ipo['listing_date'],'source_url':url,'crosscheck_url':ipo['discovery_url'],'attempts':attempts}
