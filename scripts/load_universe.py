import json
from pathlib import Path

from ipo_edge.db import connect, log_run, finish_run, upsert_ipo

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "data/backtest/universe_core.json"


def main():
    rows = json.loads(CORE.read_text())
    with connect() as conn:
        run_id = log_run(conn, "BACKTEST")
        try:
            for row in rows:
                upsert_ipo(conn, {
                    "company_name": row["company_name"],
                    "segment": row["segment"],
                    "exchange": None,
                    "issue_open_date": row["issue_open_date"],
                    "issue_close_date": row["issue_close_date"],
                    "listing_date": None,
                    "price_band_low": None,
                    "price_band_high": None,
                    "issue_price": row.get("issue_price"),
                    "issue_size": None,
                    "status": "DISCOVERED",
                })
            finish_run(conn, run_id, status="COMPLETED", discovered_count=len(rows))
            conn.commit()
            print(f"loaded_ipos={len(rows)}")
        except Exception:
            conn.rollback()
            raise


if __name__ == "__main__":
    main()
