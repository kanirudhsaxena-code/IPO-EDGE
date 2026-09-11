import json
from datetime import date
from pathlib import Path

from ipo_edge.universe import normalize_universe

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/backtest/universe_discovered.json"
CORE = ROOT / "data/backtest/universe_core.json"
OUTCOMES = ROOT / "data/backtest/outcomes_discovery_only.json"


def main():
    rows = json.loads(RAW.read_text())
    core, outcomes = normalize_universe(rows, date(2026, 4, 1), date(2026, 9, 10))
    if len(core) < 100:
        raise RuntimeError(f"Implausibly small eligible backtest universe: {len(core)}")
    CORE.write_text(json.dumps(core, indent=2, ensure_ascii=False))
    OUTCOMES.write_text(json.dumps(outcomes, indent=2, ensure_ascii=False))
    print(f"eligible_equity_ipos={len(core)} discovery_outcomes={len(outcomes)}")


if __name__ == "__main__":
    main()
