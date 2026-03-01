"""
WestervillePulse — Development & Projects Scraper
==================================================
Pulls development and construction news about Westerville, OH from:
  1. Google News RSS — targeted development/construction/planning queries
  2. The Westerville News (westervilleoh.io) — filtered for development content
  3. Columbus Underground — local development coverage

Maps each article to the Development & Projects Notion DB schema:
  Project Name, Type, Status, Location, Description, Source URL, Discovered At

Note: westerville.org returns 403 for automated requests, so the Planning
Commission and procurement pages are not directly scrapeable. Google News
reliably surfaces those stories once they hit the press.

Requirements:
    pip install requests feedparser python-dotenv

Usage:
    python scrapers/development_scraper.py
"""

import os
import sys
import json
import re
import time
import feedparser
import requests
from datetime import datetime, timezone, timedelta
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
DB_IDS_PATH    = find_db_ids_path(__file__)
SEEN_URLS_PATH = DB_IDS_PATH.parent / "seen_development_urls.json"

def load_database_id() -> str:
    if not DB_IDS_PATH.exists():
        print("  database_ids.json not found. Run setup_notion.py first.")
        sys.exit(1)
    print(f"  Using database_ids.json from: {DB_IDS_PATH}")
    with open(DB_IDS_PATH) as f:
        ids = json.load(f)
    db_id = ids.get("development_database_id")
    if not db_id:
        print("  development_database_id missing from database_ids.json.")
        sys.exit(1)
    return db_id


# ── RSS Feed Sources ──────────────────────────────────────────────────────────
# Google News RSS is the primary source since westerville.org blocks scrapers.
# Each query is tuned to surface different facets of development news.

RSS_FEEDS = [
    (
        "https://news.google.com/rss/search?"
        "q=Westerville+Ohio+construction+OR+development+OR+%22new+building%22"
        "&hl=en-US&gl=US&ceid=US:en",
        "Google News (Construction)",
    ),
    (
        "https://news.google.com/rss/search?"
        "q=Westerville+Ohio+planning+commission+OR+rezoning+OR+zoning+OR+permit"
        "&hl=en-US&gl=US&ceid=US:en",
        "Google News (Planning)",
    ),
    (
        "https://news.google.com/rss/search?"
        "q=Westerville+Ohio+road+OR+infrastructure+OR+%22under+construction%22"
        "&hl=en-US&gl=US&ceid=US:en",
        "Google News (Infrastructure)",
    ),
    (
        # Local site — general feed, filtered by dev keywords below
        "https://westervilleoh.io/feed",
        "The Westerville News",
    ),
    (
        # Columbus Underground covers local development proposals well
        "https://columbusunderground.com/feed",
        "Columbus Underground",
    ),
]

# Only keep articles containing at least one of these in title+summary
DEVELOPMENT_KEYWORDS = [
    "construction", "development", "developed", "develop",
    "planning commission", "rezoning", "zoning", "permit",
    "building", "build", "built",
    "road work", "infrastructure", "renovation", "renovate",
    "apartment", "mixed-use", "commercial", "retail",
    "project", "proposed", "approved", "groundbreaking",
    "uptown", "africa road", "city hall", "polaris",
]

# Skip articles about these — not project-relevant
EXCLUDE_KEYWORDS = [
    "obituary", "obituaries",
    "football", "basketball", "soccer", "baseball", "lacrosse",
    "playoff", "varsity",
    "for sale", "home value", "zillow", "realtor",
    "weather", "tornado",
]

# How far back to look (days)
MAX_AGE_DAYS = 90
CUTOFF_DATE  = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).date()


# ── Type detection ────────────────────────────────────────────────────────────
TYPE_KEYWORDS = {
    "Road Work":        ["road", "street", "resurfacing", "reconstruction", "intersection",
                         "roundabout", "infrastructure", "sewer", "sidewalk", "path", "trail"],
    "Park / Green Space": ["park", "green space", "trail", "recreation", "open space",
                           "retention pond", "detention basin"],
    "Renovation":       ["renovation", "renovate", "facelift", "rehabilitation", "rehab",
                         "improvement", "upgrade", "restore", "retrofit"],
    "New Construction": ["new building", "groundbreaking", "broke ground", "new construction",
                         "new development", "mixed-use", "new road", "new apartment"],
    "Residential":      ["apartment", "housing", "residential", "units", "townhome",
                         "townhouse", "condo", "dwelling"],
    "Commercial":       ["retail", "commercial", "store", "restaurant", "brewery",
                         "office", "grocery", "aldi", "shopping"],
    "Infrastructure":   ["utility", "utilities", "water", "electric", "broadband",
                         "fiber", "pipeline", "stormwater"],
}

def detect_type(title: str, summary: str) -> str:
    text = (title + " " + summary).lower()
    for project_type, keywords in TYPE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return project_type
    return "New Construction"


# ── Status detection ──────────────────────────────────────────────────────────
STATUS_KEYWORDS = {
    "Completed":          ["completed", "complete", "finished", "opened", "open",
                           "reopened", "ribbon cutting", "grand opening"],
    "Under Construction": ["under construction", "construction underway", "construction begins",
                           "groundbreaking", "broke ground", "work begins", "work underway",
                           "crews", "ongoing"],
    "Approved":           ["approved", "approval", "green light", "council approved",
                           "commission approved", "voted to approve", "passes", "passed"],
    "Proposed":           ["proposed", "proposal", "pitches", "pitched", "consider",
                           "considering", "plans to", "planning to", "wants to",
                           "seeks", "seeking", "requests", "requesting"],
    "On Hold":            ["on hold", "paused", "delayed", "postponed", "suspended",
                           "canceled", "cancelled", "withdrawn"],
}

def detect_status(title: str, summary: str) -> str:
    text = (title + " " + summary).lower()
    for status, keywords in STATUS_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return status
    return "Proposed"


# ── Location extraction ───────────────────────────────────────────────────────
# Pull the first plausible Westerville street/area name from the text.
KNOWN_LOCATIONS = [
    "Uptown", "Africa Road", "Polaris", "Sunbury Road", "Central College",
    "State Street", "Walnut Street", "Vine Street", "Park Road", "Broadway",
    "Huber Village", "Brooksedge", "Walnut Ridge", "Spring Hollow",
    "Cleveland Avenue", "Otterbein", "County Line", "Schrock Road",
]

def extract_location(title: str, summary: str) -> str:
    text = title + " " + summary
    for loc in KNOWN_LOCATIONS:
        if loc.lower() in text.lower():
            return loc
    # Fallback: look for "at <location>" or "on <street>"
    m = re.search(r"\b(?:at|on|near|along)\s+([A-Z][A-Za-z\s]{3,30}(?:Road|Street|Ave|Blvd|Dr|Lane|Rd|St|Blvd))\b", text)
    if m:
        return m.group(1).strip()
    return "Westerville, OH"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()



# ── Feed parsing ──────────────────────────────────────────────────────────────

def parse_feed(feed_url: str, source: str) -> list:
    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        print(f"\n    Warning: failed to parse {source}: {e}")
        return []

    if feed.bozo and not feed.entries:
        print(f"\n    Warning: {source} unavailable ({getattr(feed, 'status', '?')})")
        return []

    projects = []
    for entry in feed.entries:
        title   = entry.get("title", "").strip()
        url     = entry.get("link", "").strip()
        summary = _strip_html(entry.get("summary", entry.get("description", "")))[:800]

        if not title or not url:
            continue

        # Exclude non-development content
        text_lower = (title + " " + summary).lower()
        if any(kw in text_lower for kw in EXCLUDE_KEYWORDS):
            continue

        # Must contain at least one development keyword
        if not any(kw in text_lower for kw in DEVELOPMENT_KEYWORDS):
            continue

        # Must mention Westerville
        if "westerville" not in text_lower:
            continue

        # Date filter
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).date()
            except Exception:
                pass
        published = published or datetime.now(timezone.utc).date()

        if published < CUTOFF_DATE:
            continue

        projects.append({
            "title":       title,
            "url":         url,
            "summary":     summary,
            "source":      source,
            "published":   published.isoformat(),
            "type":        detect_type(title, summary),
            "status":      detect_status(title, summary),
            "location":    extract_location(title, summary),
        })

    return projects


# ── Notion writer ─────────────────────────────────────────────────────────────

def add_project_to_notion(database_id: str, project: dict) -> bool:
    props = {
        "Project Name": {
            "title": [{"text": {"content": project["title"][:200]}}]
        },
        "Type": {
            "select": {"name": project["type"]}
        },
        "Status": {
            "select": {"name": project["status"]}
        },
        "Location": {
            "rich_text": [{"text": {"content": project["location"][:500]}}]
        },
        "Description": {
            "rich_text": [{"text": {"content": project["summary"][:2000]}}]
        },
        "Source URL": {
            "url": project["url"]
        },
        "Discovered At": {
            "date": {"start": datetime.now(timezone.utc).isoformat()}
        },
    }

    payload = {"parent": {"database_id": database_id}, "properties": props}
    resp = requests.post(f"{NOTION_BASE_URL}/pages", headers=NOTION_HEADERS, json=payload)
    return resp.status_code == 200


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print()
    print("WestervillePulse -- Development & Projects Scraper")
    print("=" * 55)

    if not NOTION_TOKEN:
        print("\n  NOTION_TOKEN is not set.")
        print("   Add it to your .env file: NOTION_TOKEN=ntn_...")
        sys.exit(1)

    total_start = time.time()
    database_id = load_database_id()
    seen_urls   = load_seen_set(SEEN_URLS_PATH)

    print(f"  Writing to Notion database: {database_id}")
    print(f"  Looking back {MAX_AGE_DAYS} days (since {CUTOFF_DATE})")
    print(f"  Already seen URLs: {len(seen_urls)}\n")

    all_projects = []

    # ── Phase 1: Fetch all feeds ───────────────────────────────────────────
    phase_start = time.time()

    for feed_url, source in RSS_FEEDS:
        t = time.time()
        print(f"  Fetching: {source:<35}", end="", flush=True)
        projects     = parse_feed(feed_url, source)
        new_projects = [p for p in projects if p["url"] not in seen_urls]
        # Dedup within this batch (same URL from multiple feeds)
        for p in new_projects:
            if p["url"] not in {x["url"] for x in all_projects}:
                all_projects.append(p)
        print(f"  {len(projects)} found  ->  {len(new_projects)} new  ({elapsed(t)})")

    print(f"\n  Total new projects to add : {len(all_projects)}")
    print(f"  Fetch phase               : {elapsed(phase_start)}\n")

    if not all_projects:
        print("  Nothing new -- Notion is already up to date!")
        print(f"\n  Total runtime: {elapsed(total_start)}\n")
        return

    # ── Phase 2: Write to Notion ───────────────────────────────────────────
    phase_start = time.time()
    new_count   = 0
    skip_count  = 0

    for i, project in enumerate(all_projects, 1):
        t = time.time()
        print(f"  [{i:>3}/{len(all_projects)}] {project['title'][:55]:<55}", end="", flush=True)
        success = add_project_to_notion(database_id, project)
        print(f"  ({elapsed(t)})")

        if success:
            seen_urls.add(project["url"])
            new_count += 1
        else:
            skip_count += 1

        time.sleep(0.1)

    save_seen_set(SEEN_URLS_PATH, seen_urls)

    print()
    print("=" * 55)
    print(f"Done! Added {new_count} projects to Notion.")
    if skip_count:
        print(f"  {skip_count} failed -- check output above.")
    print(f"  Notion write phase  : {elapsed(phase_start)}")
    print(f"  Total runtime       : {elapsed(total_start)}")
    print()


if __name__ == "__main__":
    run()
