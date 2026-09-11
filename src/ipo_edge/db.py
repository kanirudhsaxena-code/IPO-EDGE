from __future__ import annotations

import json
import os
from contextlib import contextmanager

import psycopg


@contextmanager
def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    with psycopg.connect(url) as conn:
        yield conn


def log_run(conn, run_type: str, framework_version: str = "1.0") -> int:
    row = conn.execute(
        "INSERT INTO run_log (run_type, framework_version, status) VALUES (%s,%s,'STARTED') RETURNING run_id",
        (run_type, framework_version),
    ).fetchone()
    return int(row[0])


def finish_run(conn, run_id: int, *, status: str, errors: dict | None = None, **counts):
    allowed = {"discovered_count", "researched_count", "checkpoint_count", "outcomes_added"}
    sets = ["completed_at = now()", "status = %s", "errors = %s::jsonb"]
    values = [status, json.dumps(errors) if errors else None]
    for key, value in counts.items():
        if key in allowed:
            sets.append(f"{key} = %s")
            values.append(int(value))
    values.append(run_id)
    conn.execute(f"UPDATE run_log SET {', '.join(sets)} WHERE run_id = %s", values)


def upsert_ipo(conn, ipo: dict) -> int:
    row = conn.execute(
        """
        INSERT INTO ipos (company_name,segment,exchange,issue_open_date,issue_close_date,
          listing_date,price_band_low,price_band_high,issue_price,issue_size,status)
        VALUES (%(company_name)s,%(segment)s,%(exchange)s,%(issue_open_date)s,%(issue_close_date)s,
          %(listing_date)s,%(price_band_low)s,%(price_band_high)s,%(issue_price)s,%(issue_size)s,%(status)s)
        ON CONFLICT (company_name, issue_open_date) DO UPDATE SET
          segment=EXCLUDED.segment, exchange=EXCLUDED.exchange,
          issue_close_date=EXCLUDED.issue_close_date, listing_date=EXCLUDED.listing_date,
          price_band_low=EXCLUDED.price_band_low, price_band_high=EXCLUDED.price_band_high,
          issue_price=EXCLUDED.issue_price, issue_size=EXCLUDED.issue_size,
          status=EXCLUDED.status, updated_at=now()
        RETURNING ipo_id
        """, ipo).fetchone()
    return int(row[0])


def insert_checkpoint(conn, ipo_id: int, checkpoint: dict) -> int:
    payload = {"ipo_id": ipo_id, **checkpoint}
    summary = payload.get("evidence_delta_summary")
    if not isinstance(summary, str):
        payload["evidence_delta_summary"] = json.dumps(summary or {}, sort_keys=True)
    row = conn.execute(
        """
        INSERT INTO checkpoints (ipo_id,checkpoint_type,checkpoint_time,score,grade,decision,
          bear_gain_estimate,base_gain_estimate,bull_gain_estimate,confidence,hard_blocker,
          evidence_delta_summary,framework_version)
        VALUES (%(ipo_id)s,%(checkpoint_type)s,%(checkpoint_time)s,%(score)s,%(grade)s,%(decision)s,
          %(bear_gain_estimate)s,%(base_gain_estimate)s,%(bull_gain_estimate)s,%(confidence)s,
          %(hard_blocker)s,%(evidence_delta_summary)s,%(framework_version)s)
        RETURNING checkpoint_id
        """, payload).fetchone()
    return int(row[0])
