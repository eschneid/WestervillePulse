"""
WestervillePulse — Local News Scraper
======================================
Pulls local news from RSS feeds and filters for Westerville, OH relevance.
Loads results into the Notion News database.

Requirements:
    pip install requests feedparser python-dotenv

Usage:
    python scrapers/news_scraper.py
"""

import os
import sys
import json
import time
import feedparser
import requests
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import elapsed, find_db_ids_path, load_dotenv_files, load_seen_set, save_seen_set

load_dotenv_files(__file__)

NOTION_TOKEN    = os.getenv("NOTION_TOKEN", "")
NOTION_VERSION  = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_HEADERS  = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION,
}

# ── Find database_ids.json ────────────────────────────────────────────────────
DB_IDS_PATH   = find_db_ids_path(__file__)
SEEN_URLS_PATH = DB_IDS_PATH.parent / "seen_news_urls.json"

def load_database_id() -> str:
    if not DB_IDS_PATH.exists():
        print("❌  database_ids.json not found. Run setup_notion.py first.")
        sys.exit(1)
    print(f"  📂  Using database_ids.json from: {DB_IDS_PATH}")
    print(f"  📅  Only pulling articles from last {MAX_ARTICLE_AGE_DAYS} days (since {CUTOFF_DATE})")
    with open(DB_IDS_PATH) as f:
        ids = json.load(f)
    db_id = ids.get("news_database_id")
    if not db_id:
        print("❌  news_database_id missing from database_ids.json.")
        sys.exit(1)
    return db_id


# ── RSS Feed Sources ──────────────────────────────────────────────────────────
# Each entry: (feed_url, source_label, requires_keyword_filter)
# requires_keyword_filter=True means we only keep articles mentioning Westerville
RSS_FEEDS = [
    (
        # Hyperlocal WordPress site — always has /feed on WordPress
        "https://westervilleoh.io/feed",
        "The Westerville News",
        False,   # Already Westerville-specific
    ),
    (
        # Google News RSS — aggregates all sources mentioning Westerville OH
        "https://news.google.com/rss/search?q=Westerville+Ohio&hl=en-US&gl=US&ceid=US:en",
        "Google News",
        False,   # Already filtered to Westerville
    ),
    (
        # Google News RSS — Westerville city government specifically
        "https://news.google.com/rss/search?q=%22Westerville%22+%22city+council%22+OR+%22Westerville+police%22+OR+%22Westerville+schools%22&hl=en-US&gl=US&ceid=US:en",
        "Google News (Local Gov)",
        False,
    ),
    (
        # NBC4 Columbus — their actual working feed path
        "https://www.nbc4i.com/feed/",
        "NBC4",
        True,
    ),
    (
        # ABC6 Columbus local news feed
        "https://www.abc6onyourside.com/rss/news",
        "ABC6",
        True,
    ),
    (
        # 10TV local news RSS
        "https://www.10tv.com/feeds/syndication/rss/news",
        "10TV",
        True,
    ),
]

# How far back to pull articles (days)
MAX_ARTICLE_AGE_DAYS = 90
CUTOFF_DATE = (datetime.now(timezone.utc) - timedelta(days=MAX_ARTICLE_AGE_DAYS)).date()

# Keywords to filter articles from non-local feeds
WESTERVILLE_KEYWORDS = [
    "westerville",
]

# Articles containing ANY of these words in the title will be excluded
EXCLUDE_TITLE_KEYWORDS = [
    # Obituaries
    "obituary", "obituaries", "obit",
    # Sports
    "football", "basketball", "soccer", "baseball", "lacrosse", "hockey",
    "playoff", "championship", "box score", "varsity", "athlete",
    "roster", "standings", "halftime", "touchdowns", "scoring",
    "friday night rivals", "shuts out", "beats ", "defeats ",
    "wins over", "wrestling", "volleyball", "swimming", "cross country",
    "track and field", "golf team", "tennis team", "game recap", "preview:",
    "halftime score", "final score", "home game", "away game",
    # Real estate listings
    "realtor.com", "zillow", "for sale", "sq ft", "sqft", "bed, ",
    "beds,", "baths,", " mls", "listing", "home value", "home price",
    "price reduced", "open house",
    # Weather / generic non-local
    "weather forecast", "winter storm warning", "tornado watch",
    # Clearly non-Westerville
    "new york", "los angeles", "chicago", "washington dc",
]

# These must appear in title OR summary for the article to be kept
# (only applied to already-Westerville-filtered feeds for extra precision)
REQUIRE_WESTERVILLE_IN_BODY = True

# ── Category Detection ────────────────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "City Government": [
        "city council", "mayor", "ordinance", "zoning", "budget", "city hall",
        "municipal", "legislation", "ballot", "election", "vote", "commissioner",
    ],
    "Schools": [
        "school", "district", "student", "teacher", "principal", "curriculum",
        "wcs", "westerville city schools", "otterbein", "education", "graduation",
    ],
    "Public Safety": [
        "police", "fire", "crime", "arrest", "accident", "emergency", "safety",
        "sheriff", "incident", "shooting", "crash", "theft", "officer",
    ],
    "Development": [
        "construction", "development", "permit", "build", "project", "plan",
        "uptown", "rezoning", "apartment", "retail", "commercial", "opening",
    ],
    "Community": [
        "community", "volunteer", "donation", "charity", "nonprofit", "event",
        "festival", "park", "library", "celebration", "award", "recognition",
    ],
    "Business": [
        "business", "restaurant", "store", "shop", "company", "employer",
        "jobs", "hiring", "economy", "chamber", "open", "closed",
    ],
}

def detect_categories(title: str, summary: str) -> list[str]:
    """Detect categories based on keywords in title and summary."""
    text = (title + " " + summary).lower()
    matched = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched.append(category)
    return matched if matched else ["Community"]  # Default fallback


# ── RSS Parsing ───────────────────────────────────────────────────────────────

def parse_feed(feed_url: str, source: str, filter_keywords: bool) -> list[dict]:
    """Parse an RSS feed and return relevant articles."""
    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        print(f"    ⚠️  Failed to parse feed: {e}")
        return []

    if feed.bozo and not feed.entries:
        status = getattr(feed, "status", "?")
        bozo_exc = str(getattr(feed, "bozo_exception", "unknown error"))
        print(f"    ⚠️  Feed unavailable (HTTP {status}): {bozo_exc[:80]}")
        return []

    articles = []
    for entry in feed.entries:
        title   = entry.get("title", "").strip()
        url     = entry.get("link", "").strip()
        summary = entry.get("summary", entry.get("description", "")).strip()

        # Strip HTML tags from summary
        import re
        summary = re.sub(r"<[^>]+>", "", summary).strip()
        summary = summary[:500]  # Cap at 500 chars for Notion

        if not title or not url:
            continue

        # ── Exclude by title keyword ──────────────────────────────────────────
        title_lower = title.lower()
        if any(kw in title_lower for kw in EXCLUDE_TITLE_KEYWORDS):
            continue

        # ── Keyword filter for non-local feeds ────────────────────────────────
        if filter_keywords:
            text = (title + " " + summary).lower()
            if not any(kw in text for kw in WESTERVILLE_KEYWORDS):
                continue

        # ── Parse published date ──────────────────────────────────────────────
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).date()
            except Exception:
                pass
        if not published:
            published = datetime.now(timezone.utc).date()

        # ── Date filter: skip articles older than MAX_ARTICLE_AGE_DAYS ────────
        if published < CUTOFF_DATE:
            continue

        published = published.isoformat()

        articles.append({
            "title":     title,
            "url":       url,
            "summary":   summary,
            "source":    source,
            "published": published,
            "categories": detect_categories(title, summary),
        })

    return articles


# ── Notion: Write a news article ──────────────────────────────────────────────

def add_news_to_notion(database_id: str, article: dict) -> bool:
    """Insert a single news article into the Notion News database."""
    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Title": {
                "title": [{"text": {"content": article["title"][:200]}}]
            },
            "Source": {
                "select": {"name": article["source"]}
            },
            "Category": {
                "multi_select": [{"name": c} for c in article["categories"]]
            },
            "Published Date": {
                "date": {"start": article["published"]}
            },
            "URL": {
                "url": article["url"]
            },
            "Summary": {
                "rich_text": [{"text": {"content": article["summary"]}}]
            },
            "Scraped At": {
                "date": {"start": datetime.now(timezone.utc).isoformat()}
            },
            "Status": {
                "select": {"name": "New"}
            },
        },
    }

    resp = requests.post(f"{NOTION_BASE_URL}/pages", headers=NOTION_HEADERS, json=payload)
    return resp.status_code == 200



# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print()
    print("📰  WestervillePulse — Local News Scraper")
    print("=" * 55)

    if not NOTION_TOKEN:
        print("\n❌  NOTION_TOKEN is not set.")
        print("   Add it to your .env file: NOTION_TOKEN=ntn_...")
        sys.exit(1)

    total_start = time.time()
    database_id = load_database_id()
    seen_urls   = load_seen_set(SEEN_URLS_PATH)

    print(f"  🗂️   Writing to Notion database: {database_id}")
    print(f"  🔁  Already seen URLs: {len(seen_urls)}\n")

    all_articles = []

    # ── Phase 1: Fetch all feeds ──────────────────────────────────────────────
    phase_start = time.time()
    for feed_url, source, filter_keywords in RSS_FEEDS:
        t = time.time()
        print(f"  📡  {source:<25}", end="", flush=True)
        articles = parse_feed(feed_url, source, filter_keywords)
        new_articles = [a for a in articles if a["url"] not in seen_urls]
        all_articles.extend(new_articles)
        print(f"  {len(articles)} fetched  →  {len(new_articles)} new  ({elapsed(t)})")

    print(f"\n  📦  Total new articles to add : {len(all_articles)}")
    print(f"  ⏱️   Fetch phase               : {elapsed(phase_start)}\n")

    if not all_articles:
        print("  ✅  Nothing new today — Notion is already up to date!")
        print(f"\n⏱️   Total runtime: {elapsed(total_start)}\n")
        return

    # ── Phase 2: Write to Notion ──────────────────────────────────────────────
    phase_start = time.time()
    new_count   = 0
    skip_count  = 0

    for i, article in enumerate(all_articles, 1):
        t = time.time()
        print(f"  [{i:>3}/{len(all_articles)}] {article['title'][:50]:<50}", end="", flush=True)
        success = add_news_to_notion(database_id, article)
        print(f"  ({elapsed(t)})")

        if success:
            seen_urls.add(article["url"])
            new_count += 1
        else:
            skip_count += 1

        time.sleep(0.1)

    save_seen_set(SEEN_URLS_PATH, seen_urls)

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * 55)
    print(f"✅  Done! Added {new_count} articles to Notion.")
    if skip_count:
        print(f"⚠️   {skip_count} failed — check output above.")
    print(f"⏱️   Notion write phase  : {elapsed(phase_start)}")
    print(f"⏱️   Total runtime       : {elapsed(total_start)}")
    print()


if __name__ == "__main__":
    run()