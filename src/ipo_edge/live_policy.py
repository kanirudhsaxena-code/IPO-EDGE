"""Prospective V1.1 policy. No source fetching or database side effects."""
from __future__ import annotations
import hashlib
import json
import math
from urllib.parse import urlparse
from datetime import datetime, time
from zoneinfo import ZoneInfo
from .scoring import calculate_score, WEIGHTS
from .v11_candidate import institutional_demand_lane

IST = ZoneInfo('Asia/Kolkata')
CRITICAL = ('R2', 'R3', 'R4', 'R6', 'R7')

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()

def eligible_checkpoint(ipo, now, previous, final_after=time(19, 0)):
    local = now.astimezone(IST)
    closed = ipo['issue_close_date']
    if closed is None or local.date() > closed:
        return None  # Never reconstruct a live recommendation after the closing day.
    if any(p['checkpoint_type'] == 'T2_FINAL_DAY' for p in previous):
        return None
    if ipo.get('listing_date') and local.date() >= ipo['listing_date']:
        return None
    if local.date() == closed and local.time() >= final_after:
        return 'T2_FINAL_DAY'
    return 'INTERMEDIATE' if previous else 'T1_DISCOVERY'

def decide(bundle, now):
    if now.tzinfo is None:
        raise ValueError('Timezone-aware timestamp required')
    scores = bundle.get('scores', {})
    evidence = bundle.get('evidence', [])
    for e in evidence:
        if e.get('verified') and (not e.get('retrieved_at') or datetime.fromisoformat(e['retrieved_at']) > now or
                                 (e.get('published_at') and datetime.fromisoformat(e['published_at']) > now)):
            raise ValueError('Future or undated verified evidence')
    coverage = {}
    for block in CRITICAL:
        relevant = [e for e in evidence if e['block'] == block and e.get('verified')
                    and e.get('source_url') and e.get('retrieved_at')
                    and datetime.fromisoformat(e['retrieved_at']) <= now
                    and (not e.get('published_at') or datetime.fromisoformat(e['published_at']) <= now)]
        coverage[block] = bool(relevant)
    for key, value in scores.items():
        if key not in WEIGHTS or (value is not None and (not math.isfinite(value) or not 0 <= value <= 1)):
            raise ValueError('Invalid component score')
    complete = all(coverage.values())
    if bundle.get('research_complete') and set(e['block'] for e in evidence) != {f'R{i}' for i in range(1,9)}:
        raise ValueError('A complete research review must cover R1 through R8')
    if bundle.get('research_complete') and not complete:
        hosts = set()
        for a in bundle.get('attempts',[]):
            host = (urlparse(a.get('source_url','')).hostname or '').removeprefix('www.')
            for root in ('nseindia.com','bseindia.com','sebi.gov.in'):
                if host.endswith('.'+root): host=root
            if host: hosts.add(host)
        if len(hosts)<2: raise ValueError('Two independent source attempts required before final NV')
    result = calculate_score(scores, critical_evidence_verified=complete, hard_blocker=bundle.get('hard_blocker'))
    overlay = institutional_demand_lane(scores, critical_evidence_verified=complete, hard_blocker=bundle.get('hard_blocker'))
    # Candidate status does not promote an A/REJECT grade into a Subscribe recommendation.
    estimates = bundle.get('estimates')
    if estimates:
        gains=[estimates[k] for k in ('bear','base','bull')]
        if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in gains) or gains!=sorted(gains):
            raise ValueError('Invalid forecast scenarios')
        if not estimates.get('method') or not estimates.get('source_urls') or not 0<=estimates.get('confidence',-1)<=1:
            raise ValueError('Forecast needs evidence, method and confidence')
    return {'score': result.score, 'grade': result.grade, 'decision': result.decision,
            'hard_blocker': result.hard_blocker, 'coverage': coverage,
            'candidate': overlay.actionable_candidate, 'overlay_reason': overlay.reason,
            'scores': scores, 'estimates': estimates}

def validate_release(row, config):
    rules = row.get('rules_config', {})
    if row['version'] != '1.1' or row['status'] != 'FROZEN' or row['scoring_config'] != WEIGHTS:
        raise RuntimeError('Neon framework does not match V1.1')
    expected = {'grade_A_plus_plus_min':95, 'grade_A_plus_min':90, 'grade_A_min':85,
                'critical_missing_evidence_blocks_high_conviction':True,
                'canonical_efficacy_checkpoint':'T2_FINAL_DAY', 'missed_opportunity_threshold_pct':20}
    if any(rules.get(k) != v for k,v in expected.items()):
        raise RuntimeError('Base rules mismatch')
    if config.get('status') != 'PRODUCTION' or not config.get('production_activation_approved'):
        raise RuntimeError('Production approval missing')
    if rules.get('institutional_demand_lane') != config['validated_overlay'] or rules.get('evidence_recovery') != config['evidence_recovery']:
        raise RuntimeError('Production overlay/recovery mismatch')
