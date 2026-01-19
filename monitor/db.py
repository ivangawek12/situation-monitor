# monitor/db.py
from __future__ import annotations

from pathlib import Path
from typing import Optional, List
import duckdb
import pandas as pd

DB_PATH = (Path(__file__).resolve().parent.parent / "events.duckdb")

# Canonical schema order (we'll insert by name, but keep this list as truth)
EVENT_COLUMNS: List[str] = [
    "event_id",
    "ts",
    "domain",
    "title",
    "summary",
    "source_name",
    "source_url",
    "topic",
    "actors",
    "geo",
    "severity",
    "confidence",
    "priority",
    "tags",
    # geo enrichment (offline index)
    "geo_query",
    "geo_label",
    "geo_country",
    "geo_type",
    "geo_lat",
    "geo_lon",
]


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(DB_PATH))

    # Create full table (includes geo_* fields)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
          event_id VARCHAR PRIMARY KEY,
          ts TIMESTAMP,
          domain VARCHAR,
          title VARCHAR,
          summary VARCHAR,
          source_name VARCHAR,
          source_url VARCHAR,
          topic VARCHAR,
          actors VARCHAR,
          geo VARCHAR,
          severity INTEGER,
          confidence INTEGER,
          priority INTEGER,
          tags VARCHAR,

          geo_query VARCHAR,
          geo_label VARCHAR,
          geo_country VARCHAR,
          geo_type VARCHAR,
          geo_lat DOUBLE,
          geo_lon DOUBLE
        );
        """
    )

    return con


def upsert_events(df: pd.DataFrame) -> None:
    """
    Safe upsert:
    - Ensures the dataframe has the required columns (missing -> NULL)
    - Inserts by column names (NOT by position)
    """
    if df is None or df.empty:
        return

    con = connect()

    # Ensure all columns exist in df (missing -> None)
    for c in EVENT_COLUMNS:
        if c not in df.columns:
            df[c] = None

    # Keep only known columns, in canonical order
    df = df[EVENT_COLUMNS].copy()

    # Upsert manual: delete then insert
    ids = df["event_id"].astype(str).tolist()
    if ids:
        con.execute("DELETE FROM events WHERE event_id IN (SELECT * FROM UNNEST(?))", [ids])

    con.register("incoming", df)

    cols_sql = ", ".join(EVENT_COLUMNS)
    con.execute(f"INSERT INTO events ({cols_sql}) SELECT {cols_sql} FROM incoming")

    con.unregister("incoming")
    con.close()


def query_events(
    domain: Optional[str] = None,
    since_ts: Optional[str] = None,
    min_priority: int = 0
) -> pd.DataFrame:
    con = connect()
    wh = ["priority >= ?"]
    params = [min_priority]

    if domain and domain != "all":
        wh.append("domain = ?")
        params.append(domain)

    if since_ts:
        wh.append("ts >= ?")
        params.append(since_ts)

    where_sql = " AND ".join(wh)
    q = f"""
    SELECT * FROM events
    WHERE {where_sql}
    ORDER BY ts DESC, priority DESC
    """
    df = con.execute(q, params).df()
    con.close()
    return df
