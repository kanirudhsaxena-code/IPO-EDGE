from __future__ import annotations

import json
from pathlib import Path

from ipo_edge.backtest import BacktestCase, summarize_backtest


DATA = Path("data/backtest/cases.json")


def main() -> None:
    if not DATA.exists():
        print("No audited backtest cases yet. Add leakage-safe cases to data/backtest/cases.json.")
        return
    raw = json.loads(DATA.read_text())
    cases = [BacktestCase(**row) for row in raw]
    evaluated, metrics = summarize_backtest(cases)
    print(json.dumps({"cases": evaluated, "metrics": metrics.__dict__}, default=str, indent=2))


if __name__ == "__main__":
    main()
