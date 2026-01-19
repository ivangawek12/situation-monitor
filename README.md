# Ravnica Situation Monitor

**Ravnica Situation Monitor** is a local-first Python platform that ingests and visualizes **geopolitical and cyber-threat intelligence events**, enriched with automated risk scoring and offline geolocation.

It is designed for analysts and researchers who need operational visibility of global situations without relying on cloud services or external APIs.

---

## Core Capabilities

- 🌍 **Geopolitical + CTI OSINT ingestion**
- 📍 **Offline geolocation** using a global GeoNames gazetteer
- 📊 **Severity, confidence and priority scoring**
- 📈 **Spike detection and situational clustering by tags**
- 🗺️ **Dark-mode interactive world map (OpenStreetMap)**
- 🧠 **Local-first architecture powered by DuckDB**
- ⚙️ Fully reproducible and deployable offline

---

## Dashboard Overview

The monitor provides:

- A real-time event feed
- A timeline of activity over configurable time windows
- A tag-based “Active Situations” ranking
- Spike detection for anomalous event behavior
- An interactive dark map showing event geolocation and intensity
- Rankings of sources and tags for situational awareness

---

## Architecture

RSS Feeds > ingest.py > geo_lookup.py (GeoNames) > events.duckdb (DuckDB) > app.py (Streamlit + Plotly)

---

## Installation

1. Clone the repository and create a Python virtual environment:

- git clone https://github.com/yourname/situation-monitor.git
- cd situation-monitor
- python -m venv .venv
- .\.venv\Scripts\activate
- pip install -r requirements.txt

---

## Usage

1. Run ingestion to populate or refresh the local database:
    python ingest.py
2. Launch the Streamlit dashboard:
    streamlit run app.py

---

## Data Model

Each event includes:
Field	Description
event_id	Unique event identifier
ts	Timestamp
domain	geopolitics / cti
title	Event title
summary	Event summary
source_name	Feed source
priority	Computed priority score
severity	Computed severity score
confidence	Computed confidence score
geo_label	Geolocated city / region
geo_country	ISO country
geo_lat / geo_lon	Coordinates
tags	Situation classification

---
## Project Structure

/situation_monitor/
│
├── app.py                  # Main Streamlit dashboard (Situation Monitor UI)
├── ingest.py               # Entry point for RSS ingestion + scoring + geo tagging
├── events.duckdb           # Local DuckDB database (IOC + event storage)
├── config.py               # Feed configuration + domain settings
├── requirements.txt        # Python dependencies
│
├── monitor/                # Core logic: ingestion, DB ops, scoring, geolocation
│   ├── db.py               # DuckDB connection + upsert/query helpers
│   ├── ingest.py           # Feed normalization + enrichment pipeline
│   ├── rss_ingest.py       # RSS fetch + parsing layer
│   ├── geo_lookup.py       # Offline geolocation (GeoNames lookup index)
│   ├── build_geo_index.py  # Utility to build local geo index from cities dataset
│   ├── scoring.py          # Severity / Confidence / Priority logic
│   └── schema.py           # Event table schema definition
│
├── data/                   # Static lookup data for geolocation + enrichment
│   ├── geo_index.csv       # Pre-built global city + country lookup index
│   └── commands.txt        # Operational CLI commands / runbook
│
└── .venv/                  # Local Python virtual environment


---

## Use Cases
- Cyber Threat Intelligence monitoring
- Geopolitical risk tracking
- Brand protection and fraud awareness
- OSINT research and correlation
- Intelligence training and anomaly detection

---

## Philosophy
This monitor follows an intelligence-driven design:
- Structured ingestion
- Quantitative prioritization
- Visual situational encoding
- Low noise / high signal
- Analyst-centric UX

🧙‍♂️ Built for magicians who think in patterns, not in headlines.
