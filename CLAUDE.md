# WestervillePulse 🌆
**Your city's heartbeat, automated.**

Scrapes local news, new restaurants, events, and city developments
for Westerville, OH and loads them into Notion databases daily.

---

## Stack
- **Language:** Python 3.x
- **Databases:** Notion API (4 databases)
- **APIs:** Google Places API (New), Google News RSS, Eventbrite
- **Libraries:** feedparser, requests, python-dotenv (see requirements.txt)

---

## Environment Variables (.env)
```
NOTION_TOKEN=ntn_...
NOTION_PARENT_PAGE_ID=...
GOOGLE_API_KEY=AIza...
EVENTBRITE_API_KEY=...
```

---

## Project Structure
```
WestervillePulse/
├── CLAUDE.md                   ← you are here
├── .env                        ← secrets, never commit
├── .env.example                ← template
├── .gitignore
├── requirements.txt
├── setup_notion.py             ← run once to create Notion databases
├── run_all.py                  ✅ runs all 5 scrapers in sequence, logs to runs.log
├── database_ids.json           ← auto-generated Notion database IDs
├── seen_news_urls.json         ← dedup cache for news scraper
├── seen_place_ids.json         ← dedup cache for restaurants scraper
├── seen_sos_entities.json      ← dedup cache for SOS scraper (entity numbers)
├── DATA_SOURCES.md             ← notes on all data sources
├── scrapers/
│   ├── utils.py                ← shared helpers (elapsed, find_db_ids_path, load/save seen set)
│   ├── restaurants_scraper.py  ✅ complete
│   ├── news_scraper.py         ✅ complete
│   ├── events_scraper.py       ✅ complete
│   ├── development_scraper.py  ✅ complete
│   └── sos_scraper.py          ✅ complete
├── frontend/                   ← TODO: React app
│   ├── src/
│   └── package.json
└── backend/                    ← TODO: FastAPI proxy
    └── main.py
```

---

## Notion Databases
All database IDs are stored in `database_ids.json`.

| Database | Emoji | Key Fields |
|---|---|---|
| Local News | 📰 | Title, Source, Category, Published Date, URL, Summary |
| Restaurants & Businesses | 🍽️ | Name, Type, Cuisine, Address, Neighborhood, Rating, Status |
| Events & Happenings | 🎉 | Event Name, Category, Start Date, Location, Is Free, Source |
| Development & Projects | 🏗️ | Project Name, Type, Status, Location, Est. Completion |

---

## Scrapers

### restaurants_scraper.py ✅
- **API:** Google Places API (New) — `places.googleapis.com/v1/places:searchNearby`
- **Searches:** restaurant, cafe, coffee_shop, bar, bakery, sandwich_shop, pizza_restaurant
- **Radius:** 8km (~5 miles) centered on Westerville, OH (40.1262, -82.9291)
- **Dedup:** `seen_place_ids.json` — tracks Google Place IDs
- **Notes:** Uses Places API (New) field names — `displayName.text`, `formattedAddress`, `id` (not legacy `name`, `vicinity`, `place_id`)

### news_scraper.py ✅
- **Sources:**
  - `westervilleoh.io/feed` — The Westerville News (hyperlocal WordPress)
  - `news.google.com/rss/search?q=Westerville+Ohio` — Google News aggregator
  - `news.google.com/rss/search?q="Westerville"+"city+council"...` — Local gov focus
  - `nbc4i.com/feed/` — NBC4 Columbus (filtered)
  - `10tv.com/feeds/syndication/rss/news` — 10TV Columbus (filtered)
- **Filters:**
  - 90-day cutoff (no articles older than 90 days)
  - Excludes: obituaries, sports, real estate listings, non-local stories
  - Keyword exclusion list in `EXCLUDE_TITLE_KEYWORDS`
- **Dedup:** `seen_news_urls.json` — tracks article URLs

### events_scraper.py ✅
- **Sources:** Visit Westerville REST API (visitwesterville.org/wp-json/tribe/events/v1/events) + CivicPlus HTML scrape (westerville.org, parks.westerville.org)
- **Window:** next 30 days of upcoming events
- **Dedup:** `seen_event_urls.json` — tracks event slug + start date

### development_scraper.py ✅
- **Sources:** Google News RSS — construction, planning, and infrastructure queries
- **Dedup:** `seen_development_urls.json` — tracks article URLs

### sos_scraper.py ✅
- **Source:** Ohio Secretary of State business search internal API (`businesssearch.ohiosos.gov/api/Search`)
- **ZIPs:** 43081 and 43082 (Westerville, OH)
- **Filters:** Active entities, filed within last 90 days
- **Notion target:** Restaurants & Businesses DB — Status = "New Filing", Type = "Other", Notes = entity type (LLC, Corp, etc.)
- **Dedup:** `seen_sos_entities.json` — tracks Ohio entity/charter numbers
- **Graceful failure:** If the SOS API returns 403 (bot detection), prints a clear warning and exits 0 — does not crash `run_all.py`
- **If blocked:** Consider upgrading to Playwright (`pip install playwright`) for browser-based scraping

---

## TODO

### Automation
- Windows Task Scheduler to run `run_all.py` daily at 7am
- Or GitHub Actions cron job as an alternative

### Notion Dashboard Views (manual setup in Notion UI)
- News: filtered view by Category, sorted by Published Date
- Restaurants: gallery view grouped by Neighborhood
- Events: calendar view by Start Date
- Development: kanban board by Status

### React Frontend (Phase 3)
**Architecture:**
```
React App → FastAPI Backend → Notion API
```
The Notion token must stay server-side — never expose it in the React app.

**FastAPI Backend (`backend/main.py`)**
- Endpoint: `GET /api/news` — returns news articles from Notion
- Endpoint: `GET /api/restaurants` — returns restaurants from Notion
- Endpoint: `GET /api/events` — returns upcoming events from Notion
- Endpoint: `GET /api/development` — returns city projects from Notion
- Add CORS so the React app can call it
- Add simple caching (cache Notion responses for 15 mins) to avoid rate limits

**React Frontend (`frontend/`)**
- Framework: React + Tailwind CSS
- 4 main sections:
  - 📰 News feed with category filter buttons
  - 🍽️ Restaurant grid with neighborhood filter + type filter
  - 🎉 Events list sorted by date, badge for free events
  - 🏗️ Development board grouped by status
- Mobile responsive
- WestervillePulse branding (city/pulse theme)

**Hosting:**
- Frontend: Vercel (free tier, auto-deploys from GitHub)
- Backend: Railway or Render (free tier)

**To scaffold:**
```bash
claude "create a FastAPI backend in /backend with endpoints proxying our 4 Notion databases, then scaffold a React + Tailwind frontend in /frontend with a news feed, restaurant grid, events list, and development status board"
```

---

## Running the Scrapers
```bash
# Individual scrapers
python scrapers/restaurants_scraper.py
python scrapers/news_scraper.py
python scrapers/events_scraper.py
python scrapers/development_scraper.py
python scrapers/sos_scraper.py

# All at once
python run_all.py
```

---

## Notes & Gotchas
- Google Places API (New) uses different field names than legacy — `id` not `place_id`, `displayName.text` not `name`
- Notion API rejects `null` URL fields — always check before setting
- Google News RSS returns max 100 results per query
- ABC6 RSS feed returns 301 redirect — URL needs fixing
- NBC4 and 10TV return 0 Westerville matches — may need keyword tweaking
- Run `rm seen_news_urls.json` to reset news cache and re-pull all articles
- Run `rm seen_place_ids.json` to reset restaurant cache
- Run `rm seen_sos_entities.json` to reset SOS cache and re-pull all entity filings
- SOS scraper exits cleanly (code 0) if Ohio SOS blocks access — check output for the ⚠️ warning
