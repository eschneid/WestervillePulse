"""
WestervillePulse — FastAPI Backend
====================================
Proxies the 4 Notion databases with a 15-minute cache.

Usage:
    pip install -r requirements.txt
    uvicorn main:app --reload
"""

import os
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ── Config ────────────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")  # fallback to project root

NOTION_TOKEN      = os.getenv("NOTION_TOKEN", "")
NEWS_DB_ID        = os.getenv("NOTION_NEWS_DB_ID", "31441253-de01-8194-8146-da244f7cc7f3")
RESTAURANTS_DB_ID = os.getenv("NOTION_RESTAURANTS_DB_ID", "31441253-de01-8196-84e4-fcaf7236c8c3")
EVENTS_DB_ID      = os.getenv("NOTION_EVENTS_DB_ID", "31441253-de01-8114-9087-d5ec29bddd59")
DEVELOPMENT_DB_ID = os.getenv("NOTION_DEVELOPMENT_DB_ID", "31441253-de01-81fb-a51f-f4eaf265222a")

NOTION_BASE    = "https://api.notion.com/v1"
NOTION_HEADERS = {
    "Authorization":  f"Bearer {NOTION_TOKEN}",
    "Content-Type":   "application/json",
    "Notion-Version": "2022-06-28",
}

CACHE_TTL = 900  # 15 minutes

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="WestervillePulse API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to Vercel URL in production
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Cache ─────────────────────────────────────────────────────────────────────

_cache: dict[str, dict] = {}

def _cached(key: str, fetch_fn):
    entry = _cache.get(key)
    if entry and (time.time() - entry["fetched_at"]) < CACHE_TTL:
        return entry["data"]
    data = fetch_fn()
    _cache[key] = {"data": data, "fetched_at": time.time()}
    return data

# ── Notion helpers ────────────────────────────────────────────────────────────

def query_notion(db_id: str, body: dict) -> list[dict]:
    """Query a Notion database, handling pagination automatically."""
    pages = []
    body.setdefault("page_size", 100)
    while True:
        resp = requests.post(
            f"{NOTION_BASE}/databases/{db_id}/query",
            headers=NOTION_HEADERS,
            json=body,
            timeout=15,
        )
        if not resp.ok:
            raise HTTPException(status_code=502, detail=f"Notion API error: {resp.text}")
        data = resp.json()
        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        body["start_cursor"] = data["next_cursor"]
    return pages


def _text(prop) -> str:
    if not prop:
        return ""
    if prop.get("type") == "title":
        items = prop.get("title", [])
    else:
        items = prop.get("rich_text", [])
    return "".join(t.get("plain_text", "") for t in items)

def _select(prop) -> str:
    if not prop:
        return ""
    s = prop.get("select") or {}
    return s.get("name", "")

def _multi(prop) -> list[str]:
    if not prop:
        return []
    return [o["name"] for o in prop.get("multi_select", [])]

def _date(prop) -> str | None:
    if not prop:
        return None
    d = prop.get("date") or {}
    return d.get("start")

def _url(prop) -> str | None:
    if not prop:
        return None
    return prop.get("url") or None

def _bool(prop) -> bool:
    if not prop:
        return False
    return bool(prop.get("checkbox", False))

def _num(prop) -> float | None:
    if not prop:
        return None
    return prop.get("number")

# ── Endpoint implementations ──────────────────────────────────────────────────

def _fetch_news() -> list[dict]:
    pages = query_notion(NEWS_DB_ID, {
        "sorts": [{"property": "Published Date", "direction": "descending"}],
        "page_size": 50,
    })
    results = []
    for p in pages:
        props = p["properties"]
        results.append({
            "id":             p["id"],
            "title":          _text(props.get("Title")),
            "source":         _select(props.get("Source")),
            "categories":     _multi(props.get("Category")),
            "published_date": _date(props.get("Published Date")),
            "url":            _url(props.get("URL")),
            "summary":        _text(props.get("Summary")),
            "status":         _select(props.get("Status")),
            "scraped_at":     _date(props.get("Scraped At")),
        })
    return results


def _fetch_restaurants() -> list[dict]:
    pages = query_notion(RESTAURANTS_DB_ID, {
        "sorts": [{"property": "Discovered At", "direction": "descending"}],
        "page_size": 100,
    })
    results = []
    for p in pages:
        props = p["properties"]
        results.append({
            "id":            p["id"],
            "name":          _text(props.get("Name")),
            "type":          _select(props.get("Type")),
            "cuisine":       _text(props.get("Cuisine / Specialty")),
            "address":       _text(props.get("Address")),
            "neighborhood":  _select(props.get("Neighborhood")),
            "rating":        _num(props.get("Rating")),
            "website":       _url(props.get("Website")),
            "google_maps":   _url(props.get("Google Maps URL")),
            "status":        _select(props.get("Status")),
            "notes":         _text(props.get("Notes")),
            "discovered_at": _date(props.get("Discovered At")),
        })
    return results


def _fetch_events() -> list[dict]:
    today = date.today().isoformat()
    pages = query_notion(EVENTS_DB_ID, {
        "filter": {
            "or": [
                {"property": "Start Date", "date": {"on_or_after": today}},
                {"property": "Start Date", "date": {"is_empty": True}},
            ]
        },
        "sorts": [{"property": "Start Date", "direction": "ascending"}],
        "page_size": 50,
    })
    results = []
    for p in pages:
        props = p["properties"]
        results.append({
            "id":          p["id"],
            "name":        _text(props.get("Event Name")),
            "categories":  _multi(props.get("Category")),
            "start_date":  _date(props.get("Start Date")),
            "end_date":    _date(props.get("End Date")),
            "location":    _text(props.get("Location / Venue")),
            "address":     _text(props.get("Address")),
            "description": _text(props.get("Description")),
            "organizer":   _text(props.get("Organizer")),
            "event_url":   _url(props.get("Event URL")),
            "tickets_url": _url(props.get("Tickets URL")),
            "cost":        _text(props.get("Cost")),
            "is_free":     _bool(props.get("Is Free")),
            "source":      _select(props.get("Source")),
        })
    return results


def _fetch_development() -> list[dict]:
    pages = query_notion(DEVELOPMENT_DB_ID, {
        "sorts": [{"property": "Discovered At", "direction": "descending"}],
        "page_size": 50,
    })
    results = []
    for p in pages:
        props = p["properties"]
        results.append({
            "id":            p["id"],
            "name":          _text(props.get("Project Name")),
            "type":          _select(props.get("Type")),
            "status":        _select(props.get("Status")),
            "location":      _text(props.get("Location")),
            "description":   _text(props.get("Description")),
            "est_completion":_date(props.get("Est. Completion")),
            "source_url":    _url(props.get("Source URL")),
            "discovered_at": _date(props.get("Discovered At")),
        })
    return results

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/news")
def get_news():
    return _cached("news", _fetch_news)

@app.get("/api/restaurants")
def get_restaurants():
    return _cached("restaurants", _fetch_restaurants)

@app.get("/api/events")
def get_events():
    return _cached("events", _fetch_events)

@app.get("/api/development")
def get_development():
    return _cached("development", _fetch_development)
