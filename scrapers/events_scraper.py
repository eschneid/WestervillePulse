"""
WestervillePulse — Events Scraper
==================================
Pulls upcoming events from:
  1. Visit Westerville (visitwesterville.org) — Tribe Events REST API
     All events are Westerville-specific. Rich structured data.
  2. City of Westerville (westerville.org) — CivicPlus HTML scrape
     Will warn gracefully if the site blocks automated requests.
  3. Westerville Parks & Rec (parks.westerville.org) — CivicPlus HTML scrape
     Will warn gracefully if the site blocks automated requests.

Loads results into the Notion Events database.

Requirements:
    pip install requests beautifulsoup4 lxml python-dotenv brotli

Usage:
    python scrapers/events_scraper.py
"""

import os
import sys
import json
import time
import re
import html as html_module
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import elapsed, find_db_ids_path, load_dotenv_files

load_dotenv_files(__file__)

NOTION_TOKEN    = os.getenv("NOTION_TOKEN", "")
NOTION_VERSION  = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_HEADERS  = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION,
}

# ── Browser-like headers for scraping ─────────────────────────────────────────
SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
API_HEADERS = {**SCRAPE_HEADERS, "Accept": "application/json"}

# ── Find database_ids.json ────────────────────────────────────────────────────
DB_IDS_PATH    = find_db_ids_path(__file__)
SEEN_URLS_PATH = DB_IDS_PATH.parent / "seen_event_urls.json"

def load_database_id() -> str:
    if not DB_IDS_PATH.exists():
        print("  database_ids.json not found. Run setup_notion.py first.")
        sys.exit(1)
    print(f"  Using database_ids.json from: {DB_IDS_PATH}")
    with open(DB_IDS_PATH) as f:
        ids = json.load(f)
    db_id = ids.get("events_database_id")
    if not db_id:
        print("  events_database_id missing from database_ids.json.")
        sys.exit(1)
    return db_id

def load_seen_slugs() -> dict:
    """Load {slug: start_date} from disk, dropping any entries whose date has passed.

    Handles migration from the old list format (treated as empty — start fresh).
    """
    if not SEEN_URLS_PATH.exists():
        return {}
    with open(SEEN_URLS_PATH) as f:
        data = json.load(f)
    if isinstance(data, list):
        # Old format — migrate by starting fresh
        return {}
    today_str = TODAY.isoformat()
    return {slug: date for slug, date in data.items() if date >= today_str}

def save_seen_slugs(seen: dict):
    with open(SEEN_URLS_PATH, "w") as f:
        json.dump(seen, f, indent=2)


# ── Date window ───────────────────────────────────────────────────────────────
TODAY     = datetime.now(timezone.utc).date()
LOOKAHEAD = 30   # days
MAX_DATE  = TODAY + timedelta(days=LOOKAHEAD)


# ── Category detection ────────────────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "Festival":        ["festival", "fair", "parade", "celebration", "heritage"],
    "Farmers Market":  ["farmers market", "farmer's market", "farm market"],
    "Concert / Music": ["concert", "live music", "band", "jazz", "symphony", "performance"],
    "Arts & Culture":  ["art", "gallery", "museum", "theater", "theatre", "film", "exhibit", "craft"],
    "Family":          ["family", "kids", "children", "youth", "camp", "storytime"],
    "Food & Drink":    ["food", "drink", "tasting", "wine", "beer", "dinner", "brunch", "cooking"],
    "Community":       ["community", "volunteer", "town hall", "civic", "neighborhood", "meeting"],
    "Networking":      ["networking", "business", "mixer", "chamber", "professional"],
    "Sports":          ["run", "race", "5k", "walk", "fitness", "sport", "tournament", "golf", "pickleball"],
}

def detect_categories(title: str, description: str) -> list:
    text = (title + " " + description).lower()
    matched = [cat for cat, kws in CATEGORY_KEYWORDS.items() if any(kw in text for kw in kws)]
    return matched if matched else ["Community"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    text = re.sub(r"<[^>]+>", "", text or "")
    return " ".join(text.split()).strip()

def _clean_html_entities(text: str) -> str:
    """Unescape all HTML entities (numeric and named) then strip tags."""
    return _clean(html_module.unescape(text or ""))

def _abs_url(href: str, base: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return base.rstrip("/") + "/" + href.lstrip("/")

def _parse_date(text: str):
    """
    Extract a YYYY-MM-DD string from messy date text.
    Returns None if unparseable.
    """
    if not text:
        return None
    text = text.strip()

    # Already ISO
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)

    # US numeric m/d/y or m-d-y
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", text)
    if m:
        mo, day, yr = m.group(1), m.group(2), m.group(3)
        if len(yr) == 2:
            yr = "20" + yr
        try:
            return datetime(int(yr), int(mo), int(day)).date().isoformat()
        except ValueError:
            pass

    # Named-month formats
    for fmt in (
        "%B %d, %Y", "%b %d, %Y",
        "%A, %B %d, %Y", "%A, %b %d, %Y",
        "%B %d", "%b %d",
    ):
        try:
            dt = datetime.strptime(text[:40], fmt)
            if dt.year == 1900:
                dt = dt.replace(year=TODAY.year)
                if dt.date() < TODAY:
                    dt = dt.replace(year=TODAY.year + 1)
            return dt.date().isoformat()
        except ValueError:
            continue

    return None

def _in_window(iso_date) -> bool:
    if not iso_date:
        return True
    try:
        d = datetime.fromisoformat(iso_date).date()
        return TODAY <= d <= MAX_DATE
    except Exception:
        return True

def _dedup_by_slug(events: list) -> list:
    """Within a single batch, keep only the earliest upcoming occurrence per slug.

    This collapses recurring events (e.g. 30 dates of 'live-music-at-giammarcos')
    down to a single entry showing the next upcoming date.
    """
    by_slug: dict = {}
    for event in events:
        slug = _url_slug(event.get("url", ""))
        existing = by_slug.get(slug)
        if existing is None:
            by_slug[slug] = event
        else:
            # Keep whichever has the earlier (sooner) start date
            if (event.get("start_date") or "") < (existing.get("start_date") or ""):
                by_slug[slug] = event
    return list(by_slug.values())

def _url_slug(url: str) -> str:
    """Return the event slug (without date) for visitwesterville.org URLs.

    e.g. https://www.visitwesterville.org/event/live-music-at-giammarcos/2026-03-03/
         -> 'live-music-at-giammarcos'

    For any other URL, returns the full URL so dedup still works correctly.
    """
    m = re.search(r"/event/([^/]+)/", url or "")
    return m.group(1) if m else (url or "")


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 1: Visit Westerville — Tribe Events REST API
# ─────────────────────────────────────────────────────────────────────────────
#
# visitwesterville.org runs WordPress + The Events Calendar plugin.
# The REST API returns clean structured JSON with full venue and cost data.
# All events are Westerville-specific — no filtering needed.
#

VISIT_WV_API = "https://www.visitwesterville.org/wp-json/tribe/events/v1/events"

def scrape_visit_westerville() -> list:
    """Pull all upcoming Westerville events from the Visit Westerville REST API."""
    events = []
    page   = 1

    while True:
        try:
            resp = requests.get(
                VISIT_WV_API,
                headers=API_HEADERS,
                params={
                    "per_page":   50,
                    "page":       page,
                    "start_date": TODAY.isoformat(),
                    "end_date":   MAX_DATE.isoformat(),
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"\n    Warning: Visit Westerville API error (page {page}): {e}")
            break

        items = data.get("events", [])
        if not items:
            break

        for item in items:
            title = _clean_html_entities(item.get("title", ""))
            url   = item.get("url", "")
            start = (item.get("start_date") or "")[:10] or None
            end   = (item.get("end_date")   or "")[:10] or None
            desc  = _clean(item.get("description") or item.get("excerpt") or "")[:1000]

            venue_raw = item.get("venue") or {}
            venue     = venue_raw[0] if isinstance(venue_raw, list) else venue_raw
            location  = _clean_html_entities(venue.get("venue", ""))
            address  = ", ".join(filter(None, [
                _clean(venue.get("address", "")),
                _clean(venue.get("city", "")),
                _clean(venue.get("state", "")),
            ]))

            cost    = _clean(item.get("cost", ""))
            is_free = not cost or cost.strip().lower() in ("", "free", "$0", "0")

            organizer_list = item.get("organizer") or []
            organizer = ", ".join(
                _clean_html_entities(o.get("organizer", ""))
                for o in (organizer_list if isinstance(organizer_list, list) else [organizer_list])
                if o.get("organizer")
            )

            categories_raw = item.get("categories") or []
            notion_cats = detect_categories(title, desc)

            if not _in_window(start):
                continue

            events.append({
                "title":       title,
                "url":         url,
                "start_date":  start,
                "end_date":    end,
                "location":    location,
                "address":     address,
                "description": desc,
                "organizer":   organizer,
                "tickets_url": item.get("website") or None,
                "cost":        cost,
                "is_free":     is_free,
                "source":      "Other",   # "Visit Westerville" maps to Other in DB schema
                "categories":  notion_cats,
            })

        total_pages = data.get("total_pages", 1)
        if page >= total_pages:
            break
        page += 1

    return events


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 2 & 3: CivicPlus CMS (westerville.org + parks.westerville.org)
# ─────────────────────────────────────────────────────────────────────────────
#
# Both city sites run CivicPlus. These will warn gracefully if the site
# returns 403. If selectors return 0 results, inspect the page HTML and update
# the _CP_ITEM_SELECTORS list below.
#

CIVICPLUS_SOURCES = [
    {
        "label":     "City of Westerville",
        "url":       "https://www.westerville.org/i-m-looking-for-/advanced-components/event-list-view",
        "base":      "https://www.westerville.org",
        "organizer": "City of Westerville",
        "source":    "City Calendar",
        "is_free":   True,
    },
    {
        "label":     "Westerville Parks & Rec",
        "url":       (
            "https://parks.westerville.org/about-us/advanced-components/"
            "custom-news-calendar/-toggle-upcoming/-sortn-StartDate/-sortd-asc"
        ),
        "base":      "https://parks.westerville.org",
        "organizer": "Westerville Parks & Recreation",
        "source":    "Westerville Parks & Rec",
        "is_free":   True,
    },
]

# CSS selector groups tried in order; first match wins.
# Tuple: (container_sel, title_sel, date_sel, location_sel, desc_sel)
_CP_SELECTORS = [
    (
        "div.eventItem, li.eventItem",
        "a.eventItemTitle, .eventItemTitle a",
        ".eventItemDate, .fc_startdate, time",
        ".eventItemLocation, .fc_location",
        ".eventItemDescription, .fc_description",
    ),
    (
        ".CivicOutcomeListItem",
        "a",
        ".CivicOutcomeListItemDate",
        ".CivicOutcomeListItemLocation",
        ".CivicOutcomeListItemDescription",
    ),
    (
        "article, li.event",
        "h2 a, h3 a, h4 a, .title a",
        "time, .date, .event-date",
        ".location, .venue",
        ".description, .summary, p",
    ),
]

def _scrape_civicplus(cfg: dict) -> list:
    try:
        resp = requests.get(cfg["url"], headers=SCRAPE_HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"\n    Warning: {cfg['label']} unavailable: {e}")
        return []

    soup   = BeautifulSoup(resp.text, "lxml")
    events = []

    for item_sel, title_sel, date_sel, loc_sel, desc_sel in _CP_SELECTORS:
        items = soup.select(item_sel)
        if not items:
            continue

        for item in items:
            title_el = item.select_one(title_sel)
            if not title_el:
                continue

            title    = _clean(title_el.get_text())
            url      = _abs_url(title_el.get("href", ""), cfg["base"])
            date_el  = item.select_one(date_sel)
            date_str = (date_el.get("datetime") or _clean(date_el.get_text())) if date_el else ""
            start    = _parse_date(date_str)

            if not _in_window(start):
                continue

            loc_el   = item.select_one(loc_sel)
            location = _clean(loc_el.get_text()) if loc_el else ""
            desc_el  = item.select_one(desc_sel)
            desc     = _clean(desc_el.get_text()) if desc_el else ""

            events.append({
                "title":       title,
                "url":         url,
                "start_date":  start,
                "end_date":    None,
                "location":    location,
                "address":     "",
                "description": desc[:1000],
                "organizer":   cfg["organizer"],
                "tickets_url": None,
                "cost":        "",
                "is_free":     cfg["is_free"],
                "source":      cfg["source"],
                "categories":  detect_categories(title, desc),
            })

        if events:
            break   # stop trying selector groups once one works

    if not events:
        print(f"\n    Warning: No events matched for {cfg['label']}. "
              "Page may be blocked or selectors need updating.")

    return events


# ─────────────────────────────────────────────────────────────────────────────
# Notion writer
# ─────────────────────────────────────────────────────────────────────────────

def add_event_to_notion(database_id: str, event: dict) -> bool:
    """Insert a single event into the Notion Events database."""
    props = {
        "Event Name": {
            "title": [{"text": {"content": event["title"][:200]}}]
        },
        "Category": {
            "multi_select": [{"name": c} for c in event["categories"]]
        },
        "Source": {
            "select": {"name": event["source"]}
        },
        "Is Free": {
            "checkbox": bool(event["is_free"])
        },
        "Discovered At": {
            "date": {"start": datetime.now(timezone.utc).isoformat()}
        },
    }

    if event.get("start_date"):
        props["Start Date"] = {"date": {"start": event["start_date"]}}
    if event.get("end_date"):
        props["End Date"] = {"date": {"start": event["end_date"]}}
    if event.get("url"):
        props["Event URL"] = {"url": event["url"]}
    if event.get("tickets_url"):
        props["Tickets URL"] = {"url": event["tickets_url"]}
    if event.get("location"):
        props["Location / Venue"] = {
            "rich_text": [{"text": {"content": event["location"][:500]}}]
        }
    if event.get("address"):
        props["Address"] = {
            "rich_text": [{"text": {"content": event["address"][:500]}}]
        }
    if event.get("description"):
        props["Description"] = {
            "rich_text": [{"text": {"content": event["description"][:2000]}}]
        }
    if event.get("organizer"):
        props["Organizer"] = {
            "rich_text": [{"text": {"content": event["organizer"][:200]}}]
        }
    if event.get("cost"):
        props["Cost"] = {
            "rich_text": [{"text": {"content": event["cost"][:100]}}]
        }

    payload = {"parent": {"database_id": database_id}, "properties": props}
    resp = requests.post(f"{NOTION_BASE_URL}/pages", headers=NOTION_HEADERS, json=payload)
    return resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run():
    print()
    print("WestervillePulse -- Events Scraper")
    print("=" * 55)

    if not NOTION_TOKEN:
        print("\n  NOTION_TOKEN is not set.")
        print("   Add it to your .env file: NOTION_TOKEN=ntn_...")
        sys.exit(1)

    total_start = time.time()
    database_id = load_database_id()
    seen_slugs  = load_seen_slugs()

    print(f"  Writing to Notion database: {database_id}")
    print(f"  Pulling events for next {LOOKAHEAD} days (through {MAX_DATE})")
    print(f"  Already seen event types: {len(seen_slugs)}\n")

    all_events = []

    # ── Phase 1: Fetch all sources ─────────────────────────────────────────
    phase_start = time.time()

    # Visit Westerville (primary — REST API)
    t = time.time()
    print(f"  Fetching: {'Visit Westerville (API)':<35}", end="", flush=True)
    events     = scrape_visit_westerville()
    events     = _dedup_by_slug(events)
    new_events = [e for e in events if _url_slug(e.get("url", "")) not in seen_slugs]
    all_events.extend(new_events)
    print(f"  {len(events)} deduped  ->  {len(new_events)} new  ({elapsed(t)})")

    # CivicPlus city sites (best-effort HTML scrape)
    for cfg in CIVICPLUS_SOURCES:
        t = time.time()
        print(f"  Fetching: {cfg['label']:<35}", end="", flush=True)
        events     = _scrape_civicplus(cfg)
        events     = _dedup_by_slug(events)
        new_events = [e for e in events if _url_slug(e.get("url", "")) not in seen_slugs]
        all_events.extend(new_events)
        print(f"  {len(events)} deduped  ->  {len(new_events)} new  ({elapsed(t)})")

    print(f"\n  Total new events to add : {len(all_events)}")
    print(f"  Fetch phase             : {elapsed(phase_start)}\n")

    if not all_events:
        print("  Nothing new -- Notion is already up to date!")
        print(f"\n  Total runtime: {elapsed(total_start)}\n")
        return

    # ── Phase 2: Write to Notion ───────────────────────────────────────────
    phase_start = time.time()
    new_count   = 0
    skip_count  = 0

    for i, event in enumerate(all_events, 1):
        t = time.time()
        print(f"  [{i:>3}/{len(all_events)}] {event['title'][:55]:<55}", end="", flush=True)
        success = add_event_to_notion(database_id, event)
        print(f"  ({elapsed(t)})")

        if success:
            slug = _url_slug(event.get("url", ""))
            seen_slugs[slug] = event.get("start_date", "")
            new_count += 1
        else:
            skip_count += 1

        time.sleep(0.1)

    save_seen_slugs(seen_slugs)

    print()
    print("=" * 55)
    print(f"Done! Added {new_count} events to Notion.")
    if skip_count:
        print(f"  {skip_count} failed -- check output above.")
    print(f"  Notion write phase  : {elapsed(phase_start)}")
    print(f"  Total runtime       : {elapsed(total_start)}")
    print()


if __name__ == "__main__":
    run()
