# monitor/scoring.py
from datetime import datetime, timezone
from typing import List, Tuple
from dateutil import parser

def _safe_dt(dt):
    if isinstance(dt, str):
        return parser.parse(dt)
    return dt

def recency_score(ts: datetime, max_points: int = 25) -> int:
    ts = _safe_dt(ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    hours = max(0.0, (now - ts).total_seconds() / 3600.0)
    # 0h => max_points, 24h => ~half, 72h => low
    score = max_points * (1.0 / (1.0 + (hours / 24.0)))
    return int(round(min(max_points, max(0.0, score))))

def watchlist_hits(text: str, watchlist: List[str]) -> Tuple[int, List[str]]:
    t = (text or "").lower()
    hits = [w for w in watchlist if w.lower() in t]
    return len(hits), hits

def compute_priority(domain: str, title: str, summary: str, ts, watchlist: List[str], weights: dict) -> dict:
    text = f"{title}\n{summary}"
    hit_count, hits = watchlist_hits(text, watchlist)

    rscore = recency_score(ts, max_points=weights.get("recency_max", 25))
    wscore = min(weights.get("watchlist_hit", 25), hit_count * 8)

    base = weights.get("base_domain_cti", 10) if domain == "cti" else 0

    # Heurística “severity” simple: palabras gatillo
    trig = ["exploit", "0day", "zero-day", "ransomware", "breach", "apt", "sanction", "missile", "attack", "killed"]
    sev = 10 + 10 * sum(1 for k in trig if k in text.lower())
    sev = max(0, min(100, sev))

    priority = max(0, min(100, base + rscore + wscore + int(sev * 0.4)))
    return {
        "severity": sev,
        "confidence": 60,
        "priority": priority,
        "tags": list(set(hits)),
    }
