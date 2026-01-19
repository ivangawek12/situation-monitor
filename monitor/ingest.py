# ingest.py
from __future__ import annotations

import hashlib
import re
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd

from monitor.db import upsert_events
from monitor.rss_ingest import fetch_rss
from monitor.geo_lookup import lookup_candidates

SOURCES = [
    {"domain": "geopolitics", "source_name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"domain": "geopolitics", "source_name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"domain": "cti", "source_name": "The Hacker News", "url": "https://feeds.feedburner.com/TheHackersNews"},
    {"domain": "cti", "source_name": "KrebsOnSecurity", "url": "https://krebsonsecurity.com/feed/"},
]

def _safe_str(x) -> str:
    return "" if x is None else str(x)

def _hash_id(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(_safe_str(p).encode("utf-8", errors="ignore"))
        h.update(b"|")
    return h.hexdigest()[:24]

def _norm(s: str) -> str:
    s = (_safe_str(s)).strip()
    s = re.sub(r"\s+", " ", s)
    return s

# geo candidates
STOP_PLACES = {
    "monday","tuesday","wednesday","thursday","friday","saturday","sunday",
    "today","yesterday","breaking","analysis","update","exclusive","report",
    "video","live","fighting","talks","stall","says","say",
}

REGION_HINTS = [
    "middle east", "europe", "asia", "africa", "south america", "north america"
]

PLACE_PATTERNS = [
    r"\bin\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b",
    r"\bnear\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b",
    r"\bat\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b",
    r"\bfrom\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b",
]

def extract_place_candidates(title: str, summary: str) -> List[str]:
    text = f"{_safe_str(title)} {_safe_str(summary)}"
    text = re.sub(r"\s+", " ", text).strip()

    cands: List[str] = []

    low = text.lower()
    for r in REGION_HINTS:
        if r in low:
            cands.append(r.title())

    for pat in PLACE_PATTERNS:
        for m in re.finditer(pat, text):
            p = _norm(m.group(1))
            if p and p.lower() not in STOP_PLACES:
                cands.append(p)

    # Capitalized sequences (conservative)
    seqs = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", text)
    for s in seqs:
        s = _norm(s)
        if len(s) >= 3 and s.lower() not in STOP_PLACES:
            cands.append(s)

    out: List[str] = []
    seen = set()
    for c in cands:
        k = c.lower()
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out[:10]

def choose_best_geo(title: str, summary: str) -> Optional[Dict[str, Any]]:
    cands = extract_place_candidates(title, summary)
    return lookup_candidates(cands)

# scoring + tags
CTI_KEYWORDS = ["phishing", "ransomware", "malware", "cve", "breach", "ddos", "apt", "exploit"]
GEO_KEYWORDS = ["war", "missile", "strike", "protest", "ceasefire", "border", "sanctions", "military"]

def score_event(domain: str, title: str, summary: str) -> Tuple[int, int, int]:
    text = f"{title} {summary}".lower()
    base = 20
    if domain == "cti":
        hits = sum(1 for k in CTI_KEYWORDS if k in text)
        severity = min(100, base + hits * 15)
        confidence = min(100, 60 + hits * 8)
    else:
        hits = sum(1 for k in GEO_KEYWORDS if k in text)
        severity = min(100, base + hits * 15)
        confidence = min(100, 55 + hits * 8)
    priority = int(min(100, severity * 0.7 + confidence * 0.3))
    return int(severity), int(confidence), int(priority)

def build_tags(domain: str, title: str, summary: str, geo_hit: Optional[Dict[str, Any]]) -> str:
    tags: List[str] = []
    if domain:
        tags.append(domain)

    text = f"{title} {summary}".lower()
    for k in (CTI_KEYWORDS + GEO_KEYWORDS):
        if k in text:
            tags.append(k)

    if geo_hit:
        label = (geo_hit.get("label") or geo_hit.get("query") or "").strip().lower()
        if label:
            tags.append(f"geo:{label}")

        country = (geo_hit.get("country") or "").strip().lower()
        if country:
            tags.append(f"country:{country}")

    out = []
    seen = set()
    for t in tags:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return ",".join(out)

def ingest_all(limit_per_feed: int = 35) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for src in SOURCES:
        rows.extend(fetch_rss(src, limit=limit_per_feed))

    if not rows:
        return pd.DataFrame()

    out_rows = []
    geo_ok = 0
    geo_miss = 0

    for r in rows:
        domain = r.get("domain", "all")
        source_name = r.get("source_name", "")
        link = r.get("source_url", "")
        title = r.get("title", "")
        summary = r.get("summary", "")
        ts = r.get("ts")

        # ensure datetime
        ts = pd.to_datetime(ts, errors="coerce")
        if pd.isna(ts):
            continue
        ts = ts.to_pydatetime().replace(tzinfo=None)

        geo_hit = choose_best_geo(title, summary)
        if geo_hit:
            geo_ok += 1
        else:
            geo_miss += 1

        severity, confidence, priority = score_event(domain, title, summary)
        tags = build_tags(domain, title, summary, geo_hit)

        event_id = _hash_id(domain, source_name, link, title, str(ts))

        out_rows.append(
            {
                "event_id": event_id,
                "ts": ts,
                "domain": domain,
                "title": title,
                "summary": summary,
                "source_name": source_name,
                "source_url": link,
                "topic": "",
                "actors": "",
                "geo": "",
                "severity": severity,
                "confidence": confidence,
                "priority": priority,
                "tags": tags,
                "geo_query": geo_hit.get("query") if geo_hit else None,
                "geo_label": geo_hit.get("label") if geo_hit else None,
                "geo_country": geo_hit.get("country") if geo_hit else None,
                "geo_type": geo_hit.get("place_type") if geo_hit else None,
                "geo_lat": geo_hit.get("lat") if geo_hit else None,
                "geo_lon": geo_hit.get("lon") if geo_hit else None,
            }
        )

    df = pd.DataFrame(out_rows)
    print(f"[INGEST] fetched={len(df)} geo_ok={geo_ok} geo_miss={geo_miss}")
    return df

def main():
    df = ingest_all(limit_per_feed=35)
    if df.empty:
        print("[INGEST] No rows fetched.")
        return
    upsert_events(df)
    print(f"[INGEST] Upserted events: {len(df)}")

if __name__ == "__main__":
    main()
