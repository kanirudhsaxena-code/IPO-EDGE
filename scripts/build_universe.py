from __future__ import annotations

import json
from pathlib import Path

from ipo_edge.historical_universe import build_universe

MANIFEST = Path("data/backtest/universe_sources.json")
OUTPUT = Path("data/backtest/universe_discovered.json")


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    rows = build_universe(manifest["monthly_discovery_sources"])
    OUTPUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"Discovered {len(rows)} IPO rows -> {OUTPUT}")


if __name__ == "__main__":
    main()
