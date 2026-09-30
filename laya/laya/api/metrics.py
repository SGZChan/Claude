from __future__ import annotations

import time
from typing import Any

from ..memory.store import Store


def _rate(n: int, d: int) -> float:
    return round(n / d, 3) if d else 0.0


def overview(store: Store, days: int = 14) -> dict[str, Any]:
    runs = store.q("SELECT id,status,via,latency,started,feedback FROM runs WHERE status!='running' ORDER BY id")
    day0 = time.time() - (time.time() % 86400)
    ok = [r for r in runs if r["status"] == "ok"]
    today = [r for r in runs if r["started"] >= day0]
    lat = [r["latency"] for r in runs if r["latency"] is not None]
    series = []
    for i in range(days - 1, -1, -1):
        lo, hi = day0 - i * 86400, day0 - i * 86400 + 86400
        d = [r for r in runs if lo <= r["started"] < hi]
        dok = [r for r in d if r["status"] == "ok"]
        dl = [r["latency"] for r in d if r["latency"] is not None]
        series.append({"date": time.strftime("%m-%d", time.gmtime(lo)), "runs": len(d),
                       "success_rate": _rate(len(dok), len(d)),
                       "system_one_rate": _rate(sum(r["via"] == "skill" for r in dok), len(dok)),
                       "avg_latency": round(sum(dl) / len(dl), 3) if dl else 0})
    # learning curve: System-One hit rate over consecutive windows of 5 runs
    curve = []
    w = 5
    for i in range(0, len(runs), w):
        chunk = runs[i:i + w]
        curve.append({"upto_run": i + len(chunk), "system_one_rate": _rate(sum(r["via"] == "skill" for r in chunk), len(chunk)),
                      "success_rate": _rate(sum(r["status"] == "ok" for r in chunk), len(chunk))})
    return {
        "kpis": {
            "runs_total": len(runs), "runs_today": len(today),
            "success_rate": _rate(len(ok), len(runs)),
            "avg_latency": round(sum(lat) / len(lat), 3) if lat else 0,
            "system_one_rate": _rate(sum(r["via"] == "skill" for r in ok), len(ok)),
            "skills_learned": store.q("SELECT COUNT(*) c FROM skills WHERE enabled=1")[0]["c"],
            "memory_size": store.q("SELECT COUNT(*) c FROM facts")[0]["c"],
            "thumbs_up": sum(r["feedback"] > 0 for r in runs), "thumbs_down": sum(r["feedback"] < 0 for r in runs),
        },
        "daily": series, "learning_curve": curve,
    }
