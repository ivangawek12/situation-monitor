# config.py
RSS_SOURCES = [
    # Geopolítica (ejemplos)
    {"name": "BBC World", "url": "http://feeds.bbci.co.uk/news/world/rss.xml", "domain": "geopolitics"},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "domain": "geopolitics"},

    # CTI (ejemplos)
    {"name": "KrebsOnSecurity", "url": "https://krebsonsecurity.com/feed/", "domain": "cti"},
    {"name": "The Hacker News", "url": "https://thehackernews.com/feeds/posts/default?alt=rss", "domain": "cti"},
]

WATCHLIST = [
    "ransomware", "phishing", "deepfake",
    "iran", "china", "russia", "argentina",
    "election", "sanction", "ceasefire", "apt", "cve"
]


# Pesos simples
WEIGHTS = {
    "watchlist_hit": 25,
    "recency_max": 25,
    "base_domain_cti": 10,
}
