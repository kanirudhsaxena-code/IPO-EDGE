from __future__ import annotations

import math
import statistics
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import quote

import requests

UA = {"User-Agent": "Mozilla/5.0"}


def _to_epoch(d: date) -> int:
    return int(datetime.combine(d, time.min, tzinfo=timezone.utc).timestamp())


def fetch_nifty_environment(cutoff: date, timeout: int = 20) -> dict:
    """Fetch only NIFTY closes available on/before cutoff and derive 20-session regime.

    Yahoo chart data is used as a free transport source. The scoring input is entirely
    historical: no timestamp after the cutoff is admitted.
    """
    start = cutoff - timedelta(days=75)
    end = cutoff + timedelta(days=1)
    symbol = quote("^NSEI", safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={_to_epoch(start)}&period2={_to_epoch(end)}&interval=1d&events=history"
    )
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    payload = r.json()
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return {"found": False, "source_url": url, "cutoff": cutoff.isoformat()}

    node = result[0]
    timestamps = node.get("timestamp") or []
    closes = (((node.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
    points = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        if d <= cutoff:
            points.append((d, float(close)))
    if len(points) < 21:
        return {
            "found": False,
            "source_url": url,
            "cutoff": cutoff.isoformat(),
            "available_sessions": len(points),
        }

    points = points[-21:]
    first = points[0][1]
    last = points[-1][1]
    return_20d = (last / first - 1.0) * 100.0

    log_returns = [math.log(points[i][1] / points[i - 1][1]) for i in range(1, len(points))]
    daily_std = statistics.stdev(log_returns) if len(log_returns) >= 2 else 0.0
    annualized_vol = daily_std * math.sqrt(252) * 100.0

    return {
        "found": True,
        "source_url": url,
        "cutoff": cutoff.isoformat(),
        "first_session": points[0][0].isoformat(),
        "last_session": points[-1][0].isoformat(),
        "sessions": len(points),
        "nifty_20d_return_pct": round(return_20d, 4),
        "nifty_20d_vol_pct": round(annualized_vol, 4),
    }
