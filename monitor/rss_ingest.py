# monitor/rss_ingest.py
from __future__ import annotations

import feedparser
from datetime import datetime, timezone
from typing import Dict, List, Any


def _parse_ts(entry) -> datetime:
    if getattr(entry, "published_parsed", None):
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    if getattr(entry, "updated_parsed", None):
        return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def fetch_rss(source: Dict[str, str], limit: int = 35) -> List[Dict[str, Any]]:
    """
    Fetch RSS and normalize entries to a common schema.
    Expected source keys:
      - domain
      - source_name
      - url
    Returns list of dict rows: ts, title, summary, source_url, source_name, domain
    """
    url = source["url"]
    domain = source.get("domain", "all")
    source_name = source.get("source_name", "RSS")

    feed = feedparser.parse(url)

    rows: List[Dict[str, Any]] = []
    for e in feed.entries[:limit]:
        title = getattr(e, "title", "") or ""
        link = getattr(e, "link", "") or ""
        summary = getattr(e, "summary", "") or ""
        ts = _parse_ts(e)

        rows.append(
            {
                "ts": ts.replace(tzinfo=None),  # duckdb timestamp naive ok
                "title": str(title),
                "summary": str(summary),
                "source_url": str(link),
                "source_name": str(source_name),
                "domain": str(domain),
            }
        )

    return rows
