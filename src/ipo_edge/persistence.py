from __future__ import annotations

DB_BLOCKS = {
    "R1": "R1_BUSINESS",
    "R2": "R2_FINANCIALS",
    "R3": "R3_VALUATION",
    "R4": "R4_PROMOTER_ISSUE",
    "R5": "R5_ANALYST",
    "R6": "R6_INSTITUTIONAL",
    "R7": "R7_DEMAND",
    "R8": "R8_ENVIRONMENT",
}


def insert_evidence(conn, ipo_id, checkpoint_id, item):
    block = DB_BLOCKS.get(item.block, item.block)
    row = conn.execute(
        "INSERT INTO research_evidence (ipo_id,checkpoint_id,research_block,field_name,value_text,numeric_value,source_url,source_name,published_at,retrieved_at,verification_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING evidence_id",
        (ipo_id, checkpoint_id, block, item.field_name, item.value_text, item.numeric_value, item.source_url, item.source_name, item.published_at, item.retrieved_at, item.verification_status),
    ).fetchone()
    return int(row[0])


def upsert_listing_outcome(conn, ipo_id, issue_price, listing_price, listing_gain_percent, listing_date, source_url):
    row = conn.execute(
        "INSERT INTO listing_outcomes (ipo_id,issue_price,listing_price,listing_gain_percent,listing_date,source_url,verified_at) VALUES (%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (ipo_id) DO UPDATE SET issue_price=EXCLUDED.issue_price,listing_price=EXCLUDED.listing_price,listing_gain_percent=EXCLUDED.listing_gain_percent,listing_date=EXCLUDED.listing_date,source_url=EXCLUDED.source_url,verified_at=now() RETURNING outcome_id",
        (ipo_id, issue_price, listing_price, listing_gain_percent, listing_date, source_url),
    ).fetchone()
    return int(row[0])


def upsert_assessment(conn, ipo_id, checkpoint_id, outcome_id, classification, forecast_error_pp=None, missed_signal_summary=None):
    missed = classification == "MISSED_OPPORTUNITY"
    row = conn.execute(
        "INSERT INTO assessments (ipo_id,canonical_checkpoint_id,outcome_id,classification,forecast_error_pp,is_missed_opportunity,missed_signal_summary,assessed_at) VALUES (%s,%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (ipo_id) DO UPDATE SET canonical_checkpoint_id=EXCLUDED.canonical_checkpoint_id,outcome_id=EXCLUDED.outcome_id,classification=EXCLUDED.classification,forecast_error_pp=EXCLUDED.forecast_error_pp,is_missed_opportunity=EXCLUDED.is_missed_opportunity,missed_signal_summary=EXCLUDED.missed_signal_summary,assessed_at=now() RETURNING assessment_id",
        (ipo_id, checkpoint_id, outcome_id, classification, forecast_error_pp, missed, missed_signal_summary),
    ).fetchone()
    return int(row[0])
