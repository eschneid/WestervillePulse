r"""
 __        _____ ____ _____ _____ ______     _____ _     _     _____   ____  _   _ _     ____  _____
 \ \      / / __/ ___|_   _| ____|  _ \ \   / /_ _| |   | |   | ____| |  _ \| | | | |   / ___|| ____|
  \ \ /\ / /|  _\___ \ | | |  _| | |_) \ \ / / | || |   | |   |  _|   | |_) | | | | |   \___ \|  _|
   \ V  V / | |_ ___) || | | |___|  _ < \ V /  | || |___| |___| |___  |  __/| |_| | |___ ___) | |___
    \_/\_/  |____|____/ |_| |_____|_| \_\ \_/  |___|_____|_____|_____| |_|    \___/|_____|____/|_____|

WestervillePulse — Your city's heartbeat, automated.
=====================================================
Aggregates local news, new restaurants, events, and happenings
in Westerville, Ohio and loads them into a Notion database.
"""

import os
import sys
import json
import requests
from datetime import datetime, date
from typing import Optional

# ─────────────────────────────────────────────
# CONFIGURATION — fill these in before running
# ─────────────────────────────────────────────
NOTION_API_KEY    = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY", "your_notion_integration_token_here")
NOTION_PARENT_PAGE_ID = os.getenv("NOTION_PARENT_PAGE_ID", "your_parent_page_id_here")  # Page ID where databases will be created

NOTION_VERSION    = "2022-06-28"
NOTION_BASE_URL   = "https://api.notion.com/v1"

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION,
}

# ─────────────────────────────────────────────
# NOTION DATABASE SCHEMAS
# ─────────────────────────────────────────────

def create_news_database(parent_page_id: str) -> dict:
    """Creates the Local News database in Notion."""
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": "📰"},
        "title": [{"type": "text", "text": {"content": "Westerville Pulse — Local News"}}],
        "properties": {
            "Title": {"title": {}},
            "Source": {
                "select": {
                    "options": [
                        {"name": "ThisWeek News", "color": "blue"},
                        {"name": "Columbus Dispatch", "color": "orange"},
                        {"name": "10TV", "color": "green"},
                        {"name": "Westerville City", "color": "purple"},
                        {"name": "Other", "color": "gray"},
                    ]
                }
            },
            "Category": {
                "multi_select": {
                    "options": [
                        {"name": "City Government", "color": "blue"},
                        {"name": "Schools", "color": "yellow"},
                        {"name": "Public Safety", "color": "red"},
                        {"name": "Development", "color": "orange"},
                        {"name": "Community", "color": "green"},
                        {"name": "Business", "color": "pink"},
                        {"name": "Sports", "color": "purple"},
                    ]
                }
            },
            "Published Date": {"date": {}},
            "URL": {"url": {}},
            "Summary": {"rich_text": {}},
            "Scraped At": {"date": {}},
            "Status": {
                "select": {
                    "options": [
                        {"name": "New", "color": "green"},
                        {"name": "Reviewed", "color": "blue"},
                        {"name": "Archived", "color": "gray"},
                    ]
                }
            },
        },
    }
    return _create_database(payload, "Local News")


def create_restaurants_database(parent_page_id: str) -> dict:
    """Creates the New Restaurants & Businesses database in Notion."""
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": "🍽️"},
        "title": [{"type": "text", "text": {"content": "Westerville Pulse — New Restaurants & Businesses"}}],
        "properties": {
            "Name": {"title": {}},
            "Type": {
                "select": {
                    "options": [
                        {"name": "Restaurant", "color": "orange"},
                        {"name": "Café / Coffee", "color": "brown"},
                        {"name": "Bar / Brewery", "color": "yellow"},
                        {"name": "Retail", "color": "blue"},
                        {"name": "Fitness", "color": "green"},
                        {"name": "Service", "color": "gray"},
                        {"name": "Other", "color": "pink"},
                    ]
                }
            },
            "Cuisine / Specialty": {"rich_text": {}},
            "Address": {"rich_text": {}},
            "Neighborhood": {
                "select": {
                    "options": [
                        {"name": "Uptown Westerville", "color": "purple"},
                        {"name": "South Westerville", "color": "blue"},
                        {"name": "North Westerville", "color": "green"},
                        {"name": "East Westerville", "color": "orange"},
                    ]
                }
            },
            "Opening Date": {"date": {}},
            "Website": {"url": {}},
            "Phone": {"phone_number": {}},
            "Google Maps URL": {"url": {}},
            "Rating": {"number": {"format": "number"}},
            "Notes": {"rich_text": {}},
            "Discovered At": {"date": {}},
            "Status": {
                "select": {
                    "options": [
                        {"name": "Opening Soon", "color": "yellow"},
                        {"name": "Now Open", "color": "green"},
                        {"name": "Closed", "color": "red"},
                    ]
                }
            },
        },
    }
    return _create_database(payload, "New Restaurants & Businesses")


def create_events_database(parent_page_id: str) -> dict:
    """Creates the Events & Happenings database in Notion."""
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": "🎉"},
        "title": [{"type": "text", "text": {"content": "Westerville Pulse — Events & Happenings"}}],
        "properties": {
            "Event Name": {"title": {}},
            "Category": {
                "multi_select": {
                    "options": [
                        {"name": "Festival", "color": "yellow"},
                        {"name": "Farmers Market", "color": "green"},
                        {"name": "Concert / Music", "color": "purple"},
                        {"name": "Sports", "color": "orange"},
                        {"name": "Arts & Culture", "color": "pink"},
                        {"name": "Community", "color": "blue"},
                        {"name": "Food & Drink", "color": "brown"},
                        {"name": "Family", "color": "red"},
                        {"name": "Networking", "color": "gray"},
                    ]
                }
            },
            "Start Date": {"date": {}},
            "End Date": {"date": {}},
            "Location / Venue": {"rich_text": {}},
            "Address": {"rich_text": {}},
            "Description": {"rich_text": {}},
            "Organizer": {"rich_text": {}},
            "Event URL": {"url": {}},
            "Tickets URL": {"url": {}},
            "Cost": {"rich_text": {}},
            "Is Free": {"checkbox": {}},
            "Source": {
                "select": {
                    "options": [
                        {"name": "Westerville Parks & Rec", "color": "green"},
                        {"name": "Eventbrite", "color": "orange"},
                        {"name": "Facebook Events", "color": "blue"},
                        {"name": "City Calendar", "color": "purple"},
                        {"name": "Other", "color": "gray"},
                    ]
                }
            },
            "Discovered At": {"date": {}},
        },
    }
    return _create_database(payload, "Events & Happenings")


def create_development_database(parent_page_id: str) -> dict:
    """Creates the City Development & Projects database in Notion."""
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": "🏗️"},
        "title": [{"type": "text", "text": {"content": "Westerville Pulse — Development & Projects"}}],
        "properties": {
            "Project Name": {"title": {}},
            "Type": {
                "select": {
                    "options": [
                        {"name": "New Construction", "color": "orange"},
                        {"name": "Renovation", "color": "yellow"},
                        {"name": "Road Work", "color": "red"},
                        {"name": "Park / Green Space", "color": "green"},
                        {"name": "Commercial", "color": "blue"},
                        {"name": "Residential", "color": "purple"},
                        {"name": "Infrastructure", "color": "gray"},
                    ]
                }
            },
            "Status": {
                "select": {
                    "options": [
                        {"name": "Proposed", "color": "gray"},
                        {"name": "Approved", "color": "yellow"},
                        {"name": "Under Construction", "color": "orange"},
                        {"name": "Completed", "color": "green"},
                        {"name": "On Hold", "color": "red"},
                    ]
                }
            },
            "Location": {"rich_text": {}},
            "Description": {"rich_text": {}},
            "Est. Completion": {"date": {}},
            "Source URL": {"url": {}},
            "Discovered At": {"date": {}},
        },
    }
    return _create_database(payload, "Development & Projects")


# ─────────────────────────────────────────────
# HELPER: API CALL
# ─────────────────────────────────────────────

def _create_database(payload: dict, label: str) -> dict:
    """Generic helper to POST a database creation request to Notion."""
    url = f"{NOTION_BASE_URL}/databases"
    response = requests.post(url, headers=HEADERS, json=payload)
    if response.status_code == 200:
        db = response.json()
        print(f"  ✅  {label} database created → ID: {db['id']}")
        return db
    else:
        print(f"  ❌  Failed to create {label}: {response.status_code} — {response.text}")
        sys.exit(1)


# ─────────────────────────────────────────────
# SAMPLE: ADD A ROW TO A DATABASE
# ─────────────────────────────────────────────

def add_news_item(database_id: str, title: str, source: str, url: str,
                   summary: str, category: list[str], published_date: Optional[str] = None):
    """Example: Insert a news article into the News database."""
    today = date.today().isoformat()
    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Title": {"title": [{"text": {"content": title}}]},
            "Source": {"select": {"name": source}},
            "URL": {"url": url},
            "Summary": {"rich_text": [{"text": {"content": summary}}]},
            "Category": {"multi_select": [{"name": c} for c in category]},
            "Published Date": {"date": {"start": published_date or today}},
            "Scraped At": {"date": {"start": datetime.utcnow().isoformat()}},
            "Status": {"select": {"name": "New"}},
        },
    }
    url_api = f"{NOTION_BASE_URL}/pages"
    response = requests.post(url_api, headers=HEADERS, json=payload)
    if response.status_code == 200:
        print(f"  ✅  News item added: {title}")
    else:
        print(f"  ❌  Failed to add news item: {response.status_code} — {response.text}")


def add_event(database_id: str, name: str, category: list[str], start_date: str,
               location: str, description: str, event_url: str, is_free: bool = True,
               source: str = "Other"):
    """Example: Insert an event into the Events database."""
    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Event Name": {"title": [{"text": {"content": name}}]},
            "Category": {"multi_select": [{"name": c} for c in category]},
            "Start Date": {"date": {"start": start_date}},
            "Location / Venue": {"rich_text": [{"text": {"content": location}}]},
            "Description": {"rich_text": [{"text": {"content": description}}]},
            "Event URL": {"url": event_url},
            "Is Free": {"checkbox": is_free},
            "Source": {"select": {"name": source}},
            "Discovered At": {"date": {"start": datetime.utcnow().isoformat()}},
        },
    }
    url_api = f"{NOTION_BASE_URL}/pages"
    response = requests.post(url_api, headers=HEADERS, json=payload)
    if response.status_code == 200:
        print(f"  ✅  Event added: {name}")
    else:
        print(f"  ❌  Failed to add event: {response.status_code} — {response.text}")


# ─────────────────────────────────────────────
# MAIN: SETUP ALL DATABASES
# ─────────────────────────────────────────────

def setup_westerville_pulse():
    print()
    print("🌆  WestervillePulse — Setting up Notion Workspace")
    print("=" * 55)

    if NOTION_API_KEY == "your_notion_integration_token_here":
        print("\n⚠️  Please set your NOTION_TOKEN and NOTION_PARENT_PAGE_ID before running.")
        print("   You can set them as environment variables:")
        print("     export NOTION_TOKEN='ntn_xxxx'")
        print("     export NOTION_PARENT_PAGE_ID='your-page-id'")
        sys.exit(1)

    print(f"\n📋  Creating databases under page: {NOTION_PARENT_PAGE_ID}\n")

    news_db       = create_news_database(NOTION_PARENT_PAGE_ID)
    restaurants_db = create_restaurants_database(NOTION_PARENT_PAGE_ID)
    events_db      = create_events_database(NOTION_PARENT_PAGE_ID)
    dev_db         = create_development_database(NOTION_PARENT_PAGE_ID)

    db_ids = {
        "news_database_id":        news_db["id"],
        "restaurants_database_id": restaurants_db["id"],
        "events_database_id":      events_db["id"],
        "development_database_id": dev_db["id"],
    }

    # Save IDs to a local config file for use by scrapers
    with open("database_ids.json", "w") as f:
        json.dump(db_ids, f, indent=2)

    print("\n💾  Database IDs saved to database_ids.json")
    print("\n🎉  WestervillePulse workspace is ready!\n")
    print("  Next steps:")
    print("  1. Run scrapers/news_scraper.py to pull local news")
    print("  2. Run scrapers/events_scraper.py to pull upcoming events")
    print("  3. Run scrapers/restaurants_scraper.py to find new businesses")
    print("  4. Schedule with cron or GitHub Actions for daily updates\n")

    return db_ids


if __name__ == "__main__":
    setup_westerville_pulse()