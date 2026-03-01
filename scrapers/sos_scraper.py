"""
WestervillePulse — Ohio SOS Business Filings Scraper
=====================================================
Queries the Ohio Secretary of State business search for new entity registrations
in Westerville, OH ZIP codes (43081, 43082) and loads them into the Notion
Restaurants & Businesses database with Status = "New Filing".

The SOS site (businesssearch.ohiosos.gov) is a React SPA. This scraper targets
the internal API that the app uses. If the site blocks automated access (HTTP 403),
the scraper warns and exits cleanly — it does NOT crash run_all.py.

If the API endpoint or field names change, update SOS_SEARCH_URL and
the field lookups in parse_filing() below.

Requirements:
    pip install requests python-dotenv

Usage:
    python scrapers/sos_scraper.py
"""

import os
import re
import sys
import json
import time
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
DB_IDS_PATH   = find_db_ids_path(__file__)
SEEN_IDS_PATH = DB_IDS_PATH.parent / "seen_sos_entities.json"

def load_database_id() -> str:
    if not DB_IDS_PATH.exists():
        print("  database_ids.json not found. Run setup_notion.py first.")
        sys.exit(1)
    print(f"  Using database_ids.json from: {DB_IDS_PATH}")
    with open(DB_IDS_PATH) as f:
        ids = json.load(f)
    db_id = ids.get("restaurants_database_id")
    if not db_id:
        print("  restaurants_database_id missing from database_ids.json.")
        sys.exit(1)
    return db_id


# ── Ohio SOS Business Search API ─────────────────────────────────────────────
# businesssearch.ohiosos.gov is a React SPA backed by this REST API.
# Parameter names and response shape are best-effort from network inspection.
# Update SOS_SEARCH_URL or the params dict if the site changes.

SOS_SEARCH_URL   = "https://businesssearch.ohiosos.gov/api/Search"
WESTERVILLE_ZIPS = ["43081", "43082"]
MAX_AGE_DAYS     = 90
CUTOFF_DATE      = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).date()
PAGE_SIZE        = 25

# Browser-like headers to pass basic bot detection
SOS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://businesssearch.ohiosos.gov/",
    "Origin":          "https://businesssearch.ohiosos.gov",
}


def fetch_sos_page(zip_code: str, page: int = 1):
    """
    Fetch one page of recent entity filings for a ZIP code from the Ohio SOS API.
    Returns (list_of_raw_items, total_count) on success.
    Returns (None, 0) if the API is blocked or returns an unexpected response —
    callers should treat None as a signal to abort without crashing.
    """
    params = {
        "query":    "",
        "zipCode":  zip_code,
        "status":   "Active",
        "sort":     "FiledDate",
        "desc":     "true",
        "page":     page,
        "pageSize": PAGE_SIZE,
    }
    try:
        resp = requests.get(SOS_SEARCH_URL, params=params, headers=SOS_HEADERS, timeout=20)
    except requests.RequestException as e:
        print(f"\n  ⚠️  Network error querying Ohio SOS: {e}")
        return None, 0

    if resp.status_code == 403:
        print("\n  ⚠️  Ohio SOS returned 403 — automated access is blocked.")
        print("      The site may require a real browser session (bot detection).")
        print("      Consider Playwright for a future upgrade: pip install playwright")
        return None, 0

    if resp.status_code != 200:
        print(f"\n  ⚠️  Ohio SOS returned HTTP {resp.status_code}: {resp.text[:120]}")
        return None, 0

    try:
        data = resp.json()
    except ValueError:
        snippet = resp.text[:80].replace("\n", " ")
        print(f"\n  ⚠️  Ohio SOS returned non-JSON: {snippet!r}")
        print("      The API URL may have changed — check SOS_SEARCH_URL in sos_scraper.py")
        return None, 0

    # Support several common response envelope shapes
    items = (
        data.get("result")
        or data.get("results")
        or data.get("data")
        or data.get("items")
        or data.get("businesses")
        or (data if isinstance(data, list) else [])
    )
    total = int(
        data.get("totalCount")
        or data.get("total")
        or data.get("count")
        or len(items)
    )
    return items, total


def _parse_date(text: str):
    """Parse a date string (ISO, M/D/YYYY, etc.) into a date object or None."""
    if not text:
        return None
    text = text.strip()
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        pass
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2))).date()
        except ValueError:
            pass
    return None


def parse_filing(raw: dict):
    """
    Normalize a raw SOS API result into our internal format.
    Tries both camelCase and PascalCase field names since the API convention is unknown.
    Returns None if the record is too old or missing a business name.
    """
    def _get(*keys):
        for k in keys:
            v = raw.get(k)
            if v:
                return str(v).strip()
        return ""

    name = _get("entityName", "EntityName", "name", "Name")
    if not name:
        return None

    entity_num  = _get("entityNumber", "EntityNumber", "charterNumber",
                        "CharterNumber", "entityId", "EntityId")
    entity_type = _get("entityType", "EntityType", "type", "Type") or "Business"

    filed_str  = _get("filedDate", "FiledDate", "filingDate", "FilingDate",
                       "registrationDate", "RegistrationDate")
    filed_date = _parse_date(filed_str)

    # Skip records older than the cutoff (assumes API sorts newest-first)
    if filed_date and filed_date < CUTOFF_DATE:
        return None

    addr_parts = [
        _get("principalAddress", "PrincipalAddress", "address", "Address"),
        _get("principalCity",    "PrincipalCity",    "city",    "City"),
        _get("principalState",   "PrincipalState",   "state",   "State"),
        _get("principalZip",     "PrincipalZip",     "zip",     "Zip"),
    ]
    address = ", ".join(p for p in addr_parts if p)

    return {
        "name":        name,
        "entity_num":  entity_num,
        "entity_type": entity_type,
        "filed_date":  filed_date.isoformat() if filed_date else None,
        "address":     address,
    }


# ── Notion writer ─────────────────────────────────────────────────────────────

def add_filing_to_notion(database_id: str, filing: dict) -> bool:
    """Insert a single SOS business filing into the Notion Restaurants DB."""
    props = {
        "Name": {
            "title": [{"text": {"content": filing["name"][:200]}}]
        },
        "Type": {
            "select": {"name": "Other"}
        },
        "Status": {
            "select": {"name": "New Filing"}
        },
        "Notes": {
            "rich_text": [{"text": {"content": filing["entity_type"][:200]}}]
        },
        "Discovered At": {
            "date": {"start": datetime.now(timezone.utc).date().isoformat()}
        },
    }
    if filing.get("address"):
        props["Address"] = {
            "rich_text": [{"text": {"content": filing["address"][:500]}}]
        }
    if filing.get("filed_date"):
        props["Opening Date"] = {
            "date": {"start": filing["filed_date"]}
        }

    payload = {"parent": {"database_id": database_id}, "properties": props}
    resp = requests.post(f"{NOTION_BASE_URL}/pages", headers=NOTION_HEADERS, json=payload)
    return resp.status_code == 200


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print()
    print("🏢  WestervillePulse — Ohio SOS Business Filings Scraper")
    print("=" * 55)

    if not NOTION_TOKEN:
        print("\n  NOTION_TOKEN is not set.")
        print("   Add it to your .env file: NOTION_TOKEN=ntn_...")
        sys.exit(1)

    total_start = time.time()
    database_id = load_database_id()
    seen_ids    = load_seen_set(SEEN_IDS_PATH)

    print(f"  Writing to Notion database : {database_id}")
    print(f"  Looking back {MAX_AGE_DAYS} days (since {CUTOFF_DATE})")
    print(f"  Searching ZIP codes        : {', '.join(WESTERVILLE_ZIPS)}")
    print(f"  Already seen entities      : {len(seen_ids)}\n")

    all_filings  = []
    api_blocked  = False

    # ── Phase 1: Fetch from Ohio SOS ──────────────────────────────────────────
    phase_start = time.time()

    for zip_code in WESTERVILLE_ZIPS:
        t         = time.time()
        zip_count = 0
        zip_new   = 0
        print(f"  Fetching: ZIP {zip_code:<10}", end="", flush=True)

        page = 1
        while True:
            items, total = fetch_sos_page(zip_code, page)

            if items is None:
                api_blocked = True
                print("  blocked")
                break

            stop_early = False
            for raw in items:
                filing = parse_filing(raw)
                if filing is None:
                    stop_early = True   # hit records older than cutoff; stop paging
                    break
                zip_count += 1
                eid = filing["entity_num"]
                if eid not in seen_ids:
                    # Dedup within batch (same entity in both ZIPs)
                    if not any(f["entity_num"] == eid for f in all_filings):
                        all_filings.append(filing)
                        zip_new += 1

            fetched_so_far = (page - 1) * PAGE_SIZE + len(items)
            if stop_early or fetched_so_far >= total:
                break
            page += 1

        if not api_blocked:
            print(f"  {zip_count} found  ->  {zip_new} new  ({elapsed(t)})")

    print(f"\n  Total new filings to add : {len(all_filings)}")
    print(f"  Fetch phase              : {elapsed(phase_start)}\n")

    if api_blocked and not all_filings:
        print("  ⚠️  No data retrieved — Ohio SOS API was not accessible.")
        print("      See the warning above for details.")
        print(f"\n  Total runtime: {elapsed(total_start)}\n")
        return   # exit 0 — soft failure, not a crash

    if not all_filings:
        print("  Nothing new — Notion is already up to date!")
        print(f"\n  Total runtime: {elapsed(total_start)}\n")
        return

    # ── Phase 2: Write to Notion ──────────────────────────────────────────────
    phase_start = time.time()
    new_count   = 0
    skip_count  = 0

    for i, filing in enumerate(all_filings, 1):
        t = time.time()
        print(f"  [{i:>3}/{len(all_filings)}] {filing['name'][:50]:<50}", end="", flush=True)
        success = add_filing_to_notion(database_id, filing)
        print(f"  ({elapsed(t)})")

        if success:
            seen_ids.add(filing["entity_num"])
            new_count += 1
        else:
            skip_count += 1

        time.sleep(0.1)

    save_seen_set(SEEN_IDS_PATH, seen_ids)

    print()
    print("=" * 55)
    print(f"Done! Added {new_count} filings to Notion.")
    if skip_count:
        print(f"  {skip_count} failed -- check output above.")
    print(f"  Notion write phase  : {elapsed(phase_start)}")
    print(f"  Total runtime       : {elapsed(total_start)}")
    print()


if __name__ == "__main__":
    run()
