"""Consumer-neutral IPO evidence contract for the shared MDOS backbone.

This layer represents facts, source state and provenance only. It deliberately imports
no scoring, grading, recommendation, learning or checkpoint code.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from urllib.parse import urlparse

EVIDENCE_STATES = frozenset({
    "COMPLETE",
    "VERIFIED_PARTIAL",
    "CONFLICTED",
    "UNAVAILABLE",
    "RECOVERED_VIA_FALLBACK",
})

SOURCE_TYPES = frozenset({
    "OFFICIAL_REGULATORY",
    "EXCHANGE",
    "REGISTRAR",
    "REPUTABLE_SECONDARY",
    "BROKER_RESEARCH",
    "GMP_SPECIALIST",
})

SOURCE_AUTHORITY = {
    "OFFICIAL_REGULATORY": 1,
    "EXCHANGE": 2,
    "REGISTRAR": 3,
    "REPUTABLE_SECONDARY": 4,
    "BROKER_RESEARCH": 5,
    "GMP_SPECIALIST": 6,
}

IPO_VARIABLES = (
    "IPO_DISCOVERY",
    "IPO_CORE_TERMS",
    "IPO_DOCUMENTS_TIMELINE",
    "IPO_SUBSCRIPTION",
    "IPO_ANCHOR_QIB",
    "IPO_BUSINESS_QUALITY",
    "IPO_FINANCIALS",
    "IPO_VALUATION",
    "IPO_GOVERNANCE_STRUCTURE",
    "IPO_BROKER_RESEARCH",
    "IPO_GMP",
    "IPO_LISTING_OUTCOME",
    "IPO_ENVIRONMENT",
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _aware(value, field):
    if isinstance(value, datetime):
        parsed=value
    elif isinstance(value,str):
        try:
            parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
        except ValueError:
            raise ValueError(f"{field} invalid") from None
    else:
        raise ValueError(f"{field} invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} timezone required")
    return parsed.astimezone(timezone.utc)


def _https(url, field):
    if not isinstance(url,str) or urlparse(url).scheme!="https":
        raise ValueError(f"{field} must be https")
    return url


@dataclass(frozen=True)
class SourceHealth:
    name: str
    url: str
    source_type: str
    authority: int
    timestamp: str
    success: bool
    error: str | None
    recovery_attempt: int
    fallback: str | None
    final_status: str

    def validate(self):
        if not isinstance(self.name,str) or not self.name.strip():
            raise ValueError("source health name invalid")
        _https(self.url,"source health url")
        if self.source_type not in SOURCE_TYPES:
            raise ValueError("source health type invalid")
        if self.authority != SOURCE_AUTHORITY[self.source_type]:
            raise ValueError("source health authority mismatch")
        _aware(self.timestamp,"source health timestamp")
        if not isinstance(self.success,bool):
            raise ValueError("source health success invalid")
        if isinstance(self.recovery_attempt,bool) or not isinstance(self.recovery_attempt,int) or self.recovery_attempt<1:
            raise ValueError("source health recovery attempt invalid")
        if self.fallback is not None:
            _https(self.fallback,"source health fallback")
        if self.final_status not in {"SOURCE_OK","SOURCE_RECOVERED","SOURCE_FAILED"}:
            raise ValueError("source health final status invalid")
        if self.success and self.final_status=="SOURCE_FAILED":
            raise ValueError("source health contradictory")
        return self


def source_health_from_attempt(attempt):
    if not isinstance(attempt,dict):
        raise ValueError("source attempt invalid")
    source_type=attempt.get("source_type")
    if source_type not in SOURCE_TYPES:
        # Compatibility mapping for existing execution labels.
        source_type={
            "OFFICIAL_REGULATORY":"OFFICIAL_REGULATORY",
            "EXCHANGE":"EXCHANGE",
            "REPUTABLE_SECONDARY":"REPUTABLE_SECONDARY",
            "BROKER_RESEARCH":"BROKER_RESEARCH",
            "GMP_SPECIALIST":"GMP_SPECIALIST",
            "REGISTRAR":"REGISTRAR",
        }.get(source_type)
    if source_type not in SOURCE_TYPES:
        raise ValueError("unmapped source attempt type")
    row=SourceHealth(
        name=attempt.get("source_name"),
        url=attempt.get("source_url"),
        source_type=source_type,
        authority=SOURCE_AUTHORITY[source_type],
        timestamp=attempt.get("retrieved_at"),
        success=bool(attempt.get("success")),
        error=attempt.get("error"),
        recovery_attempt=attempt.get("recovery_attempt"),
        fallback=attempt.get("fallback_source_used"),
        final_status=attempt.get("final_source_status"),
    )
    return asdict(row.validate())


def verified_registrar_source(*, name, url, sebi_registration_no,
                              registry_url, verified_at):
    if not isinstance(sebi_registration_no,str) or not re.fullmatch(r"INR\d{9}",sebi_registration_no):
        raise ValueError("registrar SEBI registration invalid")
    return {
        "name": name,
        "url": _https(url,"registrar url"),
        "source_type": "REGISTRAR",
        "authority": SOURCE_AUTHORITY["REGISTRAR"],
        "sebi_registration_no": sebi_registration_no,
        "registry_url": _https(registry_url,"registrar registry url"),
        "registry_verified_at": _aware(verified_at,"registrar verification").isoformat(),
    }


def normalize_evidence_item(*, variable_id, status, values, sources,
                            observed_at, notes=None):
    if variable_id not in IPO_VARIABLES:
        raise ValueError("unknown IPO evidence variable")
    if status not in EVIDENCE_STATES:
        raise ValueError("IPO evidence state invalid")
    if not isinstance(values,dict):
        raise ValueError("IPO evidence values invalid")
    if not isinstance(sources,(list,tuple)):
        raise ValueError("IPO evidence sources invalid")
    normalized_sources=[]
    for source in sources:
        if not isinstance(source,dict):
            raise ValueError("IPO evidence source invalid")
        url=_https(source.get("url"),"IPO evidence source")
        source_type=source.get("source_type")
        if source_type not in SOURCE_TYPES:
            raise ValueError("IPO evidence source type invalid")
        authority=source.get("authority")
        if authority != SOURCE_AUTHORITY[source_type]:
            raise ValueError("IPO evidence source authority mismatch")
        digest=source.get("source_sha256")
        if not isinstance(digest,str) or not SHA256_RE.fullmatch(digest.lower()):
            raise ValueError("IPO evidence source digest invalid")
        normalized_sources.append({
            "name":source.get("name"),
            "url":url,
            "source_type":source_type,
            "authority":authority,
            "source_sha256":digest.lower(),
            "published_at":source.get("published_at"),
            "retrieved_at":_aware(source.get("retrieved_at"),"IPO evidence retrieval").isoformat(),
        })
    if status in {"COMPLETE","RECOVERED_VIA_FALLBACK"} and not normalized_sources:
        raise ValueError("verified IPO evidence requires provenance")
    return {
        "variable_id":variable_id,
        "status":status,
        "values":values,
        "sources":normalized_sources,
        "observed_at":_aware(observed_at,"IPO evidence observation").isoformat(),
        "notes":notes,
    }


def build_edge_ipo_export(*, subject, run_id, frozen_at, evidence,
                          source_health=()):
    if not isinstance(subject,dict):
        raise ValueError("IPO subject invalid")
    for field in ("id","name","segment"):
        if not isinstance(subject.get(field),str) or not subject[field].strip():
            raise ValueError(f"IPO subject {field} invalid")
    if subject["segment"] not in {"MAINBOARD","SME"}:
        raise ValueError("IPO subject segment invalid")
    if not isinstance(run_id,str) or not run_id.strip():
        raise ValueError("IPO export run id invalid")
    frozen=_aware(frozen_at,"IPO export freeze")
    if not isinstance(evidence,(list,tuple)):
        raise ValueError("IPO export evidence invalid")
    by_variable={}
    for item in evidence:
        if not isinstance(item,dict) or item.get("variable_id") not in IPO_VARIABLES:
            raise ValueError("IPO export evidence item invalid")
        if item["variable_id"] in by_variable:
            raise ValueError("duplicate IPO evidence variable")
        by_variable[item["variable_id"]]=item
    missing=sorted(set(IPO_VARIABLES)-set(by_variable))
    unresolved=sorted(
        variable for variable,item in by_variable.items()
        if item.get("status") in {"CONFLICTED","UNAVAILABLE"}
    )
    health=[source_health_from_attempt(row) for row in source_health]
    body={
        "schema":"edge-ipo-shared-evidence-export-v1",
        "consumer":"EDGE_IPO",
        "subject":subject,
        "namespace":f"EDGE_IPO:{subject['id']}",
        "run_id":run_id.strip(),
        "frozen_at":frozen.isoformat(),
        "status":"READY" if not missing and not unresolved else "BLOCKED",
        "coverage":{
            "required_variables":list(IPO_VARIABLES),
            "variables_present":sorted(by_variable),
            "missing_variables":missing,
            "unresolved_variables":unresolved,
        },
        "evidence":[by_variable[v] for v in IPO_VARIABLES if v in by_variable],
        "source_health":health,
        "methodology_applied":False,
        "scoring_applied":False,
        "grade_assigned":False,
        "recommendation_generated":False,
        "learning_promoted":False,
        "historical_checkpoint_write_enabled":False,
        "trading_enabled":False,
    }
    encoded=json.dumps(body,sort_keys=True,separators=(",",":"),default=str).encode()
    body["bundle_sha256"]=sha256(encoded).hexdigest()
    return body


def verify_edge_ipo_export(bundle):
    if not isinstance(bundle,dict) or bundle.get("schema")!="edge-ipo-shared-evidence-export-v1":
        raise ValueError("IPO export schema invalid")
    digest=bundle.get("bundle_sha256")
    if not isinstance(digest,str) or not SHA256_RE.fullmatch(digest):
        raise ValueError("IPO export digest invalid")
    body={k:v for k,v in bundle.items() if k!="bundle_sha256"}
    expected=sha256(json.dumps(body,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    if digest!=expected:
        raise ValueError("IPO export fingerprint mismatch")
    for flag in (
        "methodology_applied","scoring_applied","grade_assigned",
        "recommendation_generated","learning_promoted",
        "historical_checkpoint_write_enabled","trading_enabled",
    ):
        if bundle.get(flag) is not False:
            raise ValueError("IPO export crossed intelligence/governance boundary")
    return {
        "consumer":bundle["consumer"],
        "subject_id":bundle["subject"]["id"],
        "status":bundle["status"],
        "bundle_sha256":digest,
    }
