"""
WestervillePulse — Restaurants & Businesses Scraper
=====================================================
Uses the Google Places API to find new/recent restaurants and businesses
in Westerville, OH and loads them into the Notion database.

Requirements:
    pip install requests python-dotenv

Usage:
    python scrapers/restaurants_scraper.py
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import elapsed, find_db_ids_path, load_dotenv_files, load_seen_set, save_seen_set

load_dotenv_files(__file__)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
NOTION_TOKEN   = os.getenv("NOTION_TOKEN", "")

NOTION_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION,
}

# ── Load database IDs from setup step ────────────────────────────────────────
DB_IDS_PATH = find_db_ids_path(__file__)

def load_database_id() -> str:
    if not DB_IDS_PATH.exists():
        print(f"❌  database_ids.json not found (looked in {DB_IDS_PATH.parent}). Run setup_notion.py first.")
        sys.exit(1)
    print(f"  📂  Using database_ids.json from: {DB_IDS_PATH}")
    with open(DB_IDS_PATH) as f:
        ids = json.load(f)
    db_id = ids.get("restaurants_database_id")
    if not db_id:
        print("❌  restaurants_database_id missing from database_ids.json.")
        sys.exit(1)
    return db_id

# ── Westerville, OH center coordinates ───────────────────────────────────────
WESTERVILLE_LAT  = 40.1262
WESTERVILLE_LNG  = -82.9291
SEARCH_RADIUS_M  = 8000  # ~5 miles — covers all of Westerville

# Business type searches — using Places API (New) includedTypes
SEARCH_QUERIES = [
    ("restaurant",       "Restaurant"),
    ("cafe",             "Café / Coffee"),
    ("coffee_shop",      "Café / Coffee"),
    ("bar",              "Bar / Brewery"),
    ("bakery",           "Café / Coffee"),
    ("sandwich_shop",    "Restaurant"),
    ("pizza_restaurant", "Restaurant"),
]

PLACES_NEW_URL     = "https://places.googleapis.com/v1/places:searchNearby"
PLACES_DETAIL_URL  = "https://places.googleapis.com/v1/places"

PLACES_NEW_HEADERS = {
    "Content-Type": "application/json",
    "X-Goog-Api-Key": GOOGLE_API_KEY,
    "X-Goog-FieldMask": (
        "places.id,places.displayName,places.formattedAddress,places.location,"
        "places.rating,places.types,places.websiteUri,places.nationalPhoneNumber,"
        "places.googleMapsUri,places.businessStatus,places.primaryType"
    ),
}

# ── Google Places API (New): Nearby Search ────────────────────────────────────

def fetch_places(place_type: str) -> list[dict]:
    """Fetch nearby places using the Places API (New) — searchNearby endpoint."""
    payload = {
        "includedTypes": [place_type],
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": WESTERVILLE_LAT,
                    "longitude": WESTERVILLE_LNG,
                },
                "radius": float(SEARCH_RADIUS_M),
            }
        },
    }
    resp = requests.post(PLACES_NEW_URL, headers=PLACES_NEW_HEADERS, json=payload)
    if resp.status_code != 200:
        print(f"  ⚠️  Places API error for '{place_type}': {resp.status_code} — {resp.text[:200]}")
        return []
    return resp.json().get("places", [])


def fetch_place_details(place_id: str) -> dict:
    """For Places API (New), details are already in the search result — this is a passthrough."""
    # Details are already included via FieldMask in the search call, so no extra call needed.
    return {}


# ── Categorization helpers ────────────────────────────────────────────────────

def classify_business_type(types: list[str], default_type: str) -> str:
    """Map Google place types to our Notion category."""
    type_map = {
        "cafe": "Café / Coffee",
        "bakery": "Café / Coffee",
        "coffee_shop": "Café / Coffee",
        "bar": "Bar / Brewery",
        "night_club": "Bar / Brewery",
        "brewery": "Bar / Brewery",
        "gym": "Fitness",
        "fitness_center": "Fitness",
        "restaurant": "Restaurant",
        "meal_takeaway": "Restaurant",
        "meal_delivery": "Restaurant",
        "store": "Retail",
        "shopping_mall": "Retail",
        "clothing_store": "Retail",
        "supermarket": "Retail",
    }
    for t in types:
        if t in type_map:
            return type_map[t]
    return default_type


def classify_neighborhood(address: str) -> str:
    """Rough neighborhood classification based on address keywords."""
    address_lower = address.lower()
    if any(k in address_lower for k in ["state st", "college ave", "uptown", "home st"]):
        return "Uptown Westerville"
    if any(k in address_lower for k in ["s state", "south", "schrock", "morse"]):
        return "South Westerville"
    if any(k in address_lower for k in ["n state", "north", "africa", "otterbein"]):
        return "North Westerville"
    return "East Westerville"


def extract_cuisine(types: list[str]) -> str:
    """Best-effort cuisine/specialty extraction from Google types."""
    cuisine_types = {
        "american_restaurant": "American",
        "chinese_restaurant": "Chinese",
        "italian_restaurant": "Italian",
        "mexican_restaurant": "Mexican",
        "japanese_restaurant": "Japanese",
        "indian_restaurant": "Indian",
        "thai_restaurant": "Thai",
        "pizza": "Pizza",
        "seafood_restaurant": "Seafood",
        "steak_house": "Steakhouse",
        "sushi_restaurant": "Sushi",
        "bakery": "Bakery",
        "cafe": "Café",
        "bar": "Bar",
        "brewery": "Brewery",
        "fast_food_restaurant": "Fast Food",
        "sandwich_shop": "Sandwiches",
    }
    for t in types:
        if t in cuisine_types:
            return cuisine_types[t]
    return ""


# ── Deduplication: track already-added place IDs ─────────────────────────────

SEEN_IDS_PATH = DB_IDS_PATH.parent / "seen_place_ids.json"


# ── Notion: Write a restaurant entry ─────────────────────────────────────────

def add_restaurant_to_notion(database_id: str, place: dict, details: dict, business_type: str):
    """Insert a single restaurant/business into the Notion database."""
    # Places API (New) uses different field names than the legacy API
    name        = place.get("displayName", {}).get("text") or place.get("name", "Unknown")
    address     = place.get("formattedAddress", "")
    phone       = place.get("nationalPhoneNumber", "")
    website     = place.get("websiteUri", "")
    rating      = place.get("rating")
    maps_url    = place.get("googleMapsUri", "")
    types       = place.get("types", [])
    cuisine     = extract_cuisine(types)
    neighborhood = classify_neighborhood(address)
    discovered  = datetime.now(timezone.utc).date().isoformat()

    properties = {
        "Name":              {"title": [{"text": {"content": name}}]},
        "Type":              {"select": {"name": business_type}},
        "Address":           {"rich_text": [{"text": {"content": address}}]},
        "Neighborhood":      {"select": {"name": neighborhood}},
        "Google Maps URL":   {"url": maps_url if maps_url else None},
        "Discovered At":     {"date": {"start": discovered}},
        "Status":            {"select": {"name": "Now Open"}},
    }

    if cuisine:
        properties["Cuisine / Specialty"] = {"rich_text": [{"text": {"content": cuisine}}]}
    if phone:
        properties["Phone"] = {"phone_number": phone}
    if website:
        properties["Website"] = {"url": website}
    if rating is not None:
        properties["Rating"] = {"number": rating}

    # Remove None url values (Notion rejects null URLs)
    if properties["Google Maps URL"]["url"] is None:
        del properties["Google Maps URL"]

    payload = {
        "parent": {"database_id": database_id},
        "properties": properties,
    }

    resp = requests.post(f"{NOTION_BASE_URL}/pages", headers=NOTION_HEADERS, json=payload)
    if resp.status_code == 200:
        print(f"    ✅  Added: {name} ({business_type})")
        return True
    else:
        print(f"    ❌  Failed to add {name}: {resp.status_code} — {resp.text[:120]}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print()
    print("🍽️   WestervillePulse — Restaurants & Businesses Scraper")
    print("=" * 55)

    if not GOOGLE_API_KEY:
        print("\n❌  GOOGLE_API_KEY is not set.")
        print("   Add it to your .env file: GOOGLE_API_KEY=AIza...")
        sys.exit(1)

    if not NOTION_TOKEN:
        print("\n❌  NOTION_TOKEN is not set.")
        print("   Add it to your .env file: NOTION_TOKEN=ntn_...")
        sys.exit(1)

    total_start = time.time()
    database_id = load_database_id()
    seen_ids    = load_seen_set(SEEN_IDS_PATH)

    print(f"\n📍  Searching within 5 miles of Westerville, OH center...")
    print(f"🗂️   Writing to Notion database: {database_id}\n")

    all_places = {}
    new_count  = 0
    skip_count = 0

    # ── Phase 1: Fetch from Google Places ────────────────────────────────────
    phase_start = time.time()
    for place_type, display_type in SEARCH_QUERIES:
        t = time.time()
        print(f"  🔍  Searching: {place_type:<20}", end="", flush=True)
        places = fetch_places(place_type)
        for p in places:
            pid = p.get("id") or p.get("place_id") or p.get("name")
            if pid and pid not in all_places:
                all_places[pid] = (p, display_type)
        print(f"{len(places)} results  ({elapsed(t)})")

    to_process = {pid: v for pid, v in all_places.items() if pid not in seen_ids}
    print(f"\n  📦  Unique places found : {len(all_places)}")
    print(f"  🔁  Already in Notion   : {len(all_places) - len(to_process)}")
    print(f"  🆕  New to add          : {len(to_process)}")
    print(f"  ⏱️   Search phase        : {elapsed(phase_start)}\n")

    # ── Phase 2: Write to Notion ──────────────────────────────────────────────
    phase_start = time.time()
    for i, (place_id, (place, default_type)) in enumerate(to_process.items(), 1):
        name = place.get("displayName", {}).get("text") or place.get("name") or "Unknown"
        t = time.time()
        print(f"  [{i:>3}/{len(to_process)}] {name[:45]:<45}", end="", flush=True)

        business_type = classify_business_type(place.get("types", []), default_type)
        success = add_restaurant_to_notion(database_id, place, {}, business_type)
        print(f"  ({elapsed(t)})")

        if success:
            seen_ids.add(place_id)
            new_count += 1
        else:
            skip_count += 1

        time.sleep(0.1)

    save_seen_set(SEEN_IDS_PATH, seen_ids)

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * 55)
    print(f"✅  Done! Added {new_count} new businesses to Notion.")
    if skip_count:
        print(f"⚠️   {skip_count} entries failed — check output above.")
    print(f"⏱️   Notion write phase  : {elapsed(phase_start)}")
    print(f"⏱️   Total runtime       : {elapsed(total_start)}")
    print()


if __name__ == "__main__":
    run()
