import json
from pathlib import Path
from ipo_edge.db import connect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/backtest/development_research_queue.json"


def main():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT ipo_id, company_name, segment, issue_open_date, issue_close_date, issue_price
            FROM ipos
            WHERE issue_open_date BETWEEN DATE '2026-04-01' AND DATE '2026-06-30'
            ORDER BY issue_open_date, company_name
            """
        ).fetchall()
    queue = []
    for ipo_id, name, segment, opened, closed, price in rows:
        queue.append({
            "ipo_id": ipo_id,
            "company_name": name,
            "segment": segment,
            "issue_open_date": opened.isoformat(),
            "issue_close_date": closed.isoformat() if closed else None,
            "issue_price": float(price) if price is not None else None,
            "required_blocks": ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"],
            "t1_cutoff": opened.isoformat(),
            "t2_cutoff": closed.isoformat() if closed else opened.isoformat(),
            "status": "PENDING_RESEARCH",
        })
    if len(queue) != 56:
        raise RuntimeError(f"Expected 56 development IPOs, found {len(queue)}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(queue, indent=2, ensure_ascii=False))
    print(f"development_queue={len(queue)}")


if __name__ == "__main__":
    main()
