# monitor/geo_lookup.py
from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any, List
import re
import pandas as pd
from rapidfuzz import process, fuzz

_GEO_PATH = Path("data/geo_index.csv")
_GEO_DF: Optional[pd.DataFrame] = None
_GEO_SET = None
_GEO_CHOICES: Optional[List[str]] = None


def _norm(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.strip().lower()
    # remove simple punctuation that often appears in headlines
    s = re.sub(r"[\,\.\;\:\(\)\[\]\{\}\!\?\"\'`]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _load_geo() -> pd.DataFrame:
    global _GEO_DF, _GEO_SET, _GEO_CHOICES
    if _GEO_DF is not None:
        return _GEO_DF
    if not _GEO_PATH.exists():
        raise FileNotFoundError(f"Missing geo index: {_GEO_PATH}. Run your geo index builder first.")
    df = pd.read_csv(_GEO_PATH, dtype={"alias": str, "country_code": str})

    df["alias_norm"] = df["alias"].fillna("").astype(str).apply(_norm)
    df = df[df["alias_norm"] != ""].copy()
    df = df.reset_index(drop=True)

    _GEO_SET = set(df["alias_norm"].unique())
    _GEO_CHOICES = df["alias_norm"].tolist()
    _GEO_DF = df
    return df


def _row_to_hit(query: str, row: pd.Series) -> Dict[str, Any]:
    return {
        "query": query,
        "label": str(row.get("alias") or query),
        "lat": float(row["lat"]),
        "lon": float(row["lon"]),
        "country": str(row.get("country_code") or ""),
        "place_type": "geonames",
    }


def lookup_place_exact(name: str) -> Optional[Dict[str, Any]]:
    if not name:
        return None

    df = _load_geo()
    key = _norm(name)
    if not key or key not in _GEO_SET:
        return None

    hit = df[df["alias_norm"] == key].head(1)
    if hit.empty:
        return None

    return _row_to_hit(name, hit.iloc[0])


def lookup_candidates(cands: List[str]) -> Optional[Dict[str, Any]]:
    if not cands:
        return None

    df = _load_geo()
    for c in cands:
        hit = lookup_place_exact(c)
        if hit:
            return hit

        key = _norm(c)
        if not key:
            continue
        match = process.extractOne(
            key,
            _GEO_CHOICES,
            scorer=fuzz.WRatio,
            score_cutoff=90,
        )
        if match:
            _, _, idx = match
            return _row_to_hit(c, df.iloc[idx])
    return None
