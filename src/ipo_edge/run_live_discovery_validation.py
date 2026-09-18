"""Validation-only live IPO discovery/source-health audit. No DB writes or scoring."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from ipo_edge.evidence_contract import source_health_from_attempt
from ipo_edge.live_sources import PublicWeb

OUT=Path(".ipo_edge/discovery_validation/result.json")


def run():
    now=datetime.now(timezone.utc)
    provider=PublicWeb()
    rows, attempts, complete=provider.discover(now)
    report=provider.discovery_report
    health=[]
    health_errors=[]
    for attempt in attempts:
        try:
            health.append(source_health_from_attempt(attempt))
        except Exception as exc:
            health_errors.append({
                "source_name":attempt.get("source_name"),
                "source_url":attempt.get("source_url"),
                "source_type":attempt.get("source_type"),
                "error":type(exc).__name__,
            })
    segment_status={
        key:value.get("status")
        for key,value in report.get("segments",{}).items()
    }
    result={
        "schema":"ipo-edge-live-discovery-validation-v1",
        "captured_at":now.isoformat(),
        "status":"PASS" if complete and not report.get("conflicts") and not health_errors else "PARTIAL",
        "coverage_status":report.get("coverage_status"),
        "segments":report.get("segments",{}),
        "segment_status":segment_status,
        "conflicts":report.get("conflicts",[]),
        "discovered_count":len(rows),
        "discovered":[{
            "company_name":row.get("company_name"),
            "segment":row.get("segment"),
            "issue_open_date":str(row.get("issue_open_date")),
            "issue_close_date":str(row.get("issue_close_date")),
            "discovery_url":row.get("discovery_url"),
        } for row in rows],
        "source_health":health,
        "source_health_errors":health_errors,
        "raw_attempts":attempts,
        "diagnostic_observations":[{
            "source_name":obs.get("source_name"),
            "source_url":obs.get("source_url"),
            "ok":obs.get("ok"),
            "provenance_group":obs.get("provenance_group"),
            "enumerated":obs.get("enumerated"),
            "issue_corroboration":obs.get("issue_corroboration"),
            "segments_searched":obs.get("segments_searched",[]),
            "unresolved":obs.get("unresolved",[]),
            "rows":[{
                "company_name":r.get("company_name"),
                "segment":r.get("segment"),
                "issue_open_date":str(r.get("issue_open_date")),
                "issue_close_date":str(r.get("issue_close_date")),
            } for r in obs.get("rows",[])],
        } for obs in report.get("observations",[])],
        "historical_write_enabled":False,
        "scoring_applied":False,
        "grade_assigned":False,
        "recommendation_generated":False,
        "production_activation_allowed":False,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,sort_keys=True,separators=(",",":"),default=str)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True,separators=(",",":"),default=str))
    return result

if __name__=="__main__":
    run()
