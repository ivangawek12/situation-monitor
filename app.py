# app.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from datetime import datetime, timedelta

from monitor.db import query_events


# ----------------------------
# THEME + UX (dark)
# ----------------------------
def apply_theme():
    st.markdown(
        """
        <style>
        :root{
          --bg:#0b0f14;
          --panel:#0f1620;
          --panel2:#121c28;
          --text:#e8edf2;
          --muted:#9aa7b2;
          --border:rgba(255,255,255,.10);
          --accent:#7fb3ff;
        }

        html, body, [class*="stApp"]{
          background: var(--bg) !important;
          color: var(--text) !important;
          font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif !important;
        }

        [data-testid="stSidebar"]{
          background: var(--panel) !important;
          border-right: 1px solid var(--border) !important;
        }
        [data-testid="stSidebar"] *{
          color: var(--text) !important;
        }

        [data-baseweb="select"] > div{
          background: var(--panel2) !important;
          border: 1px solid var(--border) !important;
        }
        [data-baseweb="popover"] *{
          background: var(--panel2) !important;
          color: var(--text) !important;
        }

        .stButton > button{
          background: var(--panel2) !important;
          color: var(--text) !important;
          border: 1px solid var(--border) !important;
          border-radius: 10px !important;
        }

        h1,h2,h3,h4,p,li,span,div,label{ color: var(--text) !important; }
        a{ color: var(--accent) !important; text-decoration:none; }
        a:hover{ text-decoration:underline; }

        hr{ border-color: var(--border) !important; }

        [data-testid="stMetric"]{
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 12px !important;
          padding: 14px 14px !important;
        }
        [data-testid="stMetricValue"]{
          font-size: 2.2rem !important;
          font-weight: 800 !important;
          line-height: 1.05 !important;
        }

        [data-testid="stDataFrame"], [data-testid="stExpander"]{
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 12px !important;
          overflow: hidden !important;
        }

        .js-plotly-plot .plotly .main-svg{ background: rgba(0,0,0,0) !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ----------------------------
# Helpers
# ----------------------------
def exploded_view(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["tags"] = d.get("tags", "").fillna("").astype(str)
    d["tag_list"] = d["tags"].apply(lambda x: [t.strip() for t in x.split(",") if t.strip()])
    d = d.explode("tag_list")
    d["situation"] = d.apply(
        lambda r: r["tag_list"] if isinstance(r["tag_list"], str) and r["tag_list"] else f"untagged:{r['domain']}",
        axis=1,
    )
    d["ts"] = pd.to_datetime(d["ts"], errors="coerce")
    d = d.dropna(subset=["ts"])
    d["date"] = d["ts"].dt.date
    return d


def build_active_situations_exploded(df: pd.DataFrame, top_n: int = 12) -> pd.DataFrame:
    d = exploded_view(df)
    agg = (
        d.groupby("situation")
        .agg(
            events=("event_id", "count"),
            max_priority=("priority", "max"),
            avg_priority=("priority", "mean"),
            last_ts=("ts", "max"),
            top_source=("source_name", lambda x: x.value_counts().index[0] if len(x) else ""),
        )
        .reset_index()
    )
    agg["situation_score"] = (agg["max_priority"] * 1.0) + (agg["events"] * 2.0) + (agg["avg_priority"] * 0.2)
    agg = agg.sort_values(["situation_score", "max_priority", "events"], ascending=False).head(top_n)
    return agg


def detect_spikes(
    d_exploded: pd.DataFrame,
    group_col: str = "situation",
    lookback_days: int = 14,
    baseline_days: int = 7,
    min_events_total: int = 3,
    top_n: int = 12,
) -> pd.DataFrame:
    if d_exploded.empty:
        return pd.DataFrame()

    now = pd.Timestamp.now()
    cutoff_recent = now - pd.Timedelta(hours=24)
    cutoff_lookback = now - pd.Timedelta(days=lookback_days)
    cutoff_baseline_start = now - pd.Timedelta(days=baseline_days + 1)
    cutoff_baseline_end = cutoff_recent

    x = d_exploded[d_exploded["ts"] >= cutoff_lookback].copy()
    daily = x.groupby([group_col, "date"]).size().reset_index(name="count")
    if daily.empty:
        return pd.DataFrame()

    recent = (
        d_exploded[d_exploded["ts"] >= cutoff_recent]
        .groupby(group_col)
        .size()
        .rename("recent_24h")
        .reset_index()
    )

    baseline_slice = d_exploded[(d_exploded["ts"] >= cutoff_baseline_start) & (d_exploded["ts"] < cutoff_baseline_end)]
    baseline_daily = baseline_slice.groupby([group_col, "date"]).size().reset_index(name="count")
    baseline = baseline_daily.groupby(group_col)["count"].mean().rename("baseline_avg").reset_index()

    stats = daily.groupby(group_col)["count"].agg(mu="mean", sigma="std", total="sum", days="count").reset_index()

    out = stats.merge(recent, on=group_col, how="left").merge(baseline, on=group_col, how="left")
    out["recent_24h"] = out["recent_24h"].fillna(0).astype(int)
    out["baseline_avg"] = out["baseline_avg"].fillna(0.0)

    latest_date = daily["date"].max()
    today = daily[daily["date"] == latest_date][[group_col, "count"]].rename(columns={"count": "today_count"})
    out = out.merge(today, on=group_col, how="left")
    out["today_count"] = out["today_count"].fillna(0).astype(int)

    out["sigma"] = out["sigma"].replace(0, np.nan)
    out["z_today"] = ((out["today_count"] - out["mu"]) / out["sigma"]).fillna(0.0)

    out["pct_vs_baseline"] = np.where(
        out["baseline_avg"] > 0,
        (out["recent_24h"] - out["baseline_avg"]) / out["baseline_avg"] * 100.0,
        np.where(out["recent_24h"] > 0, 999.0, 0.0),
    )

    out = out[out["total"] >= min_events_total].copy()
    out["spike_score"] = (out["z_today"] * 10.0) + (out["recent_24h"] * 3.0) + (out["pct_vs_baseline"] * 0.05)

    out = out.sort_values("spike_score", ascending=False).head(top_n)
    out = out.rename(columns={group_col: "group"})
    out = out[["group", "recent_24h", "baseline_avg", "pct_vs_baseline", "z_today", "total"]]
    out["baseline_avg"] = out["baseline_avg"].round(2)
    out["pct_vs_baseline"] = out["pct_vs_baseline"].round(1)
    out["z_today"] = out["z_today"].round(2)
    return out


# ----------------------------
# Overview: timeline + text-cloud
# ----------------------------
TIME_WINDOWS = {
    "24h": timedelta(hours=24),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
    "15d": timedelta(days=15),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}

def top_tags_counts(df: pd.DataFrame, top_n: int = 60) -> pd.DataFrame:
    tags = df.get("tags", "").fillna("").astype(str).str.split(",")
    tag_series = tags.explode()
    tag_series = tag_series[tag_series != ""]
    vc = tag_series.value_counts().head(top_n)
    return vc.rename_axis("tag").reset_index(name="count")


def render_text_cloud(tag_df: pd.DataFrame):
    if tag_df.empty:
        st.caption("No tags in this window.")
        return

    dfw = tag_df.head(45).copy()
    cmin, cmax = dfw["count"].min(), dfw["count"].max()

    def scale(c):
        if cmax == cmin:
            return 22
        return 14 + (c - cmin) * (46 - 14) / (cmax - cmin)

    dfw["size"] = dfw["count"].apply(scale)

    # spiral-ish deterministic layout
    n = len(dfw)
    angles = np.linspace(0, 6 * np.pi, n)
    radii = np.linspace(0.15, 1.0, n)
    dfw["x"] = np.cos(angles) * radii
    dfw["y"] = np.sin(angles) * radii

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dfw["x"],
            y=dfw["y"],
            mode="text",
            text=dfw["tag"],
            textfont=dict(size=dfw["size"]),
            hovertext=[f"{t}: {c}" for t, c in zip(dfw["tag"], dfw["count"])],
            hoverinfo="text",
        )
    )

    fig.update_layout(
        template="plotly_dark",
        height=280,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)


# ----------------------------
# Map: OpenStreet dark + domain markers + risk buckets
# ----------------------------
DOMAIN_COLOR = {
    "geopolitics": "#f97316",  # orange
    "cti": "#22c55e",          # green
    "all": "#38bdf8",          # cyan
}

def openstreet_dark_map(df_map: pd.DataFrame):
    if df_map.empty:
        st.caption("No geo-coded events in this window yet (ingest will populate geo_lat/geo_lon).")
        return

    traces = []

    # domain only; color driven by domain
    df_map = df_map.copy()
    df_map["geo_lat"] = pd.to_numeric(df_map["geo_lat"], errors="coerce")
    df_map["geo_lon"] = pd.to_numeric(df_map["geo_lon"], errors="coerce")
    df_map = df_map.dropna(subset=["geo_lat", "geo_lon"])
    if df_map.empty:
        st.caption("No valid geo coordinates to display.")
        return
    for dom in sorted(df_map["domain"].unique()):
        sub = df_map[df_map["domain"] == dom].copy()
        if sub.empty:
            continue

        color = DOMAIN_COLOR.get(dom, "#38bdf8")
        stars = ["*"] * len(sub)

        # text labels: geo_label (or country)
        traces.append(
            go.Scattermap(
                lat=sub["geo_lat"],
                lon=sub["geo_lon"],
                mode="text",
                text=stars,
                textposition="middle center",
                textfont=dict(size=30, color=color),
                hovertext=sub["title"],
                customdata=np.stack(
                    [
                        sub["source_name"].astype(str),
                        sub["domain"].astype(str),
                        sub["priority"].fillna(0).astype(int).astype(str),
                        sub["severity"].fillna(0).astype(int).astype(str),
                        sub["geo_label"].fillna("").astype(str),
                        sub["geo_country"].fillna("").astype(str),
                        sub["source_url"].fillna("").astype(str),
                        sub["tags"].fillna("").astype(str),
                        sub["summary"].fillna("").astype(str),
                    ],
                    axis=1,
                ),
                hovertemplate=(
                    "<b>%{hovertext}</b><br>"
                    "Source: %{customdata[0]}<br>"
                    "Domain: %{customdata[1]}<br>"
                    "Priority: %{customdata[2]} | Severity: %{customdata[3]}<br>"
                    "Location: %{customdata[4]} (%{customdata[5]})<br>"
                    "%{customdata[8]}<br>"
                    "<extra></extra>"
                ),
                name=f"{dom}",
                showlegend=True,
            )
        )

    fig = go.Figure(traces)
    fig.update_layout(
        template="plotly_dark",
        height=900,  # dominates the scene
        margin=dict(l=0, r=0, t=0, b=0),
        map=dict(
            style="carto-darkmatter",
            zoom=1.08,
            center=dict(lat=18, lon=0),
        ),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=0.98,
            xanchor="right",
            x=0.99,
            bgcolor="rgba(0,0,0,0.35)",
            bordercolor="rgba(255,255,255,0.10)",
            borderwidth=1,
            font=dict(size=12),
        ),
    )

    st.plotly_chart(fig, use_container_width=True)


# ----------------------------
# Table styling helper
# ----------------------------
def apply_heat_styles(df: pd.DataFrame):
    d = df.copy()
    for col in ["priority", "severity"]:
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0)

    sty = d.style
    if "priority" in d.columns:
        sty = sty.background_gradient(subset=["priority"], cmap="Blues")
    if "severity" in d.columns:
        sty = sty.background_gradient(subset=["severity"], cmap="Reds")

    sty = sty.set_table_styles(
        [
            {"selector": "th", "props": "background-color:#0f1620;color:#e8edf2;border:1px solid rgba(255,255,255,.10);"},
            {"selector": "td", "props": "background-color:#0b0f14;color:#e8edf2;border:1px solid rgba(255,255,255,.07);"},
            {"selector": "table", "props": "border-collapse:collapse;border:1px solid rgba(255,255,255,.10);"},
        ]
    )
    return sty


# ----------------------------
# App
# ----------------------------
st.set_page_config(page_title="Ravnica Situation Monitor", layout="wide")
apply_theme()

st.title("Ravnica Situation Monitor")

with st.sidebar:
    st.header("Core Filters")
    domain = st.selectbox("Domain", ["all", "geopolitics", "cti"], index=0)
    min_priority = st.slider("Minimum priority", 0, 100, 0)

    st.divider()
    st.header("Top Panel")
    top_window = st.selectbox("Time range", ["24h", "3d", "7d", "15d", "30d", "90d"], index=2)

    st.divider()
    st.header("Spikes")
    lookback_days = st.selectbox("Lookback (days)", [7, 14, 21, 30], index=1)
    baseline_days = st.selectbox("Baseline (days)", [3, 7, 10, 14], index=1)

    st.divider()
    show_map = st.checkbox("Show Map", value=True)
    st.caption("Tip: run `python ingest.py` to refresh the feed.")


max_td = max(TIME_WINDOWS.values())
since_query = (datetime.now() - max_td).strftime("%Y-%m-%d %H:%M:%S")
df = query_events(domain=domain, since_ts=since_query, min_priority=min_priority)

if df.empty:
    st.warning("No events yet for these filters. Run `python ingest.py`.")
    st.stop()

df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
df = df.dropna(subset=["ts"])

df_ex = exploded_view(df)

window_td = TIME_WINDOWS[top_window]
cutoff = pd.Timestamp.now() - window_td
df_top = df[df["ts"] >= cutoff].copy()

# ----------------------------
# Overview
# ----------------------------
st.subheader("Overview")

m1, m2, m3 = st.columns([2, 2, 1])

with m3:
    st.metric("Total events", int(len(df_top)))

with m1:
    if df_top.empty:
        st.caption("No events in selected range.")
    else:
        dtime = df_top.copy()
        if window_td <= timedelta(days=3):
            dtime["ts_hour"] = dtime["ts"].dt.floor("H")
            series = dtime.groupby("ts_hour").size().reset_index(name="count")
            fig_t = px.line(series, x="ts_hour", y="count")
        else:
            dtime["ts_day"] = dtime["ts"].dt.floor("D")
            series = dtime.groupby("ts_day").size().reset_index(name="count")
            fig_t = px.bar(series, x="ts_day", y="count")

        fig_t.update_layout(
            template="plotly_dark",
            height=280,
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis_title="",
            yaxis_title="Events",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_t, use_container_width=True)

with m2:
    tag_df = top_tags_counts(df_top, top_n=60)
    render_text_cloud(tag_df)

# ----------------------------
# Map (dominant)
# ----------------------------
if show_map:
    st.subheader("Map — Situation Picture")
    # only plot rows with geo_lat/lon
    df_map = df_top.dropna(subset=["geo_lat", "geo_lon"]).copy()
    openstreet_dark_map(df_map)
    st.divider()

# ----------------------------
# Main layout
# ----------------------------
left, right = st.columns([2, 1])

with left:
    st.subheader("Feed")
    show = df_top.sort_values(["ts", "priority"], ascending=[False, False]).head(40)
    for _, r in show.iterrows():
        st.markdown(
            f"**[{r['title']}]({r['source_url']})**  \n"
            f"{r['source_name']} — {r['domain']} — {r['ts']}  \n"
            f"Priority: **{r['priority']}** | Severity: {r['severity']} | Tags: `{r['tags']}`"
        )
        if r.get("summary"):
            st.caption(str(r["summary"])[:350])
        st.divider()

with right:
    st.subheader("Spikes (24h vs baseline)")
    spikes_tags = detect_spikes(
        df_ex,
        group_col="situation",
        lookback_days=int(lookback_days),
        baseline_days=int(baseline_days),
        min_events_total=3,
        top_n=10,
    )
    if spikes_tags.empty:
        st.caption("No spikes detected yet (need more history / events).")
    else:
        st.dataframe(spikes_tags, use_container_width=True)

    st.divider()

    st.subheader("Spikes by Domain")
    spikes_domain = detect_spikes(
        df_ex,
        group_col="domain",
        lookback_days=int(lookback_days),
        baseline_days=int(baseline_days),
        min_events_total=3,
        top_n=5,
    )
    if spikes_domain.empty:
        st.caption("No domain-level spikes yet.")
    else:
        st.dataframe(spikes_domain, use_container_width=True)

    st.divider()

    st.subheader("Active Situations")
    sit = build_active_situations_exploded(df_top if not df_top.empty else df, top_n=12)
    sub_ex = exploded_view(df_top if not df_top.empty else df)

    for _, s in sit.iterrows():
        label = s["situation"]
        st.markdown(
            f"**{label}**  \n"
            f"Events: **{int(s['events'])}** | Max priority: **{int(s['max_priority'])}**  \n"
            f"Last: {s['last_ts']} | Top source: {s['top_source']}"
        )
        with st.expander("Show items"):
            items = (
                sub_ex[sub_ex["situation"] == label]
                .sort_values(["priority", "ts"], ascending=[False, False])
                .drop_duplicates(subset=["event_id"])
                .head(10)
            )
            for _, rr in items.iterrows():
                st.markdown(
                    f"- **[{rr['title']}]({rr['source_url']})** — {rr['source_name']} — {rr['ts']} — Priority **{rr['priority']}**"
                )
        st.divider()

    st.subheader("Rankings")
    tag_df_all = top_tags_counts(df_top if not df_top.empty else df, top_n=15)
    st.write("**Top Tags**")
    st.dataframe(tag_df_all.set_index("tag"), use_container_width=True)

    st.write("**Top Sources**")
    st.dataframe(
        (df_top if not df_top.empty else df)["source_name"].value_counts().head(15).rename("count"),
        use_container_width=True,
    )

# ----------------------------
# Events table + download
# ----------------------------
st.subheader("Events Table")

table_df = df_top[["ts", "domain", "priority", "severity", "source_name", "title", "source_url", "tags"]].copy()
table_df = table_df.sort_values(["ts", "priority"], ascending=[False, False])

# Use st.write(Styler) to ensure styles render
st.write(apply_heat_styles(table_df))

csv_bytes = table_df.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download events CSV",
    data=csv_bytes,
    file_name="events_lookup.csv",
    mime="text/csv",
)
