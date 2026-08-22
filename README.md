# 🌆 WestervillePulse

**Your city's heartbeat, automated.**

WestervillePulse scrapes local news, new restaurants and business filings, events,
and development projects for **Westerville, Ohio**, loads them into Notion databases,
and emails a daily digest. A FastAPI backend and React frontend expose the same data
as a web dashboard.

Runs daily at 7am EDT via GitHub Actions.

---

## How it works

```
 RSS feeds ─┐
 Google Places API ─┤
 Ohio SOS API ──────┼──► scrapers/*.py ──► Notion (4 databases) ──► FastAPI ──► React app
 Visit Westerville ─┤                            │
 City calendars ────┘                            └──► digest.py ──► daily email (Gmail SMTP)
```

`run_all.py` runs the five scrapers plus the digest in sequence. One failing scraper
doesn't stop the others; every run appends a summary to `runs.log`.

---

## Quick start

```bash
git clone https://github.com/eschneid/WestervillePulse.git
cd WestervillePulse

pip install -r requirements.txt

cp env.example .env      # then fill in your keys
python setup_notion.py   # one time — creates the Notion databases, writes database_ids.json

python run_all.py
```

### Environment variables

Copy `env.example` to `.env` and fill in:

| Variable | Required | Purpose |
|---|---|---|
| `NOTION_TOKEN` | ✅ | Notion integration token ([create one](https://www.notion.so/my-integrations)) |
| `NOTION_PARENT_PAGE_ID` | ✅ | Page the databases get created under (`setup_notion.py` only) |
| `GOOGLE_API_KEY` | ✅ | Google Places API (New) — restaurants scraper |
| `ANTHROPIC_API_KEY` | optional | Claude-written article summaries + digest intro (falls back to plain text) |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | optional | Gmail SMTP for the daily digest ([app password](https://myaccount.google.com/apppasswords), not your login password) |
| `EVENTBRITE_API_KEY` | optional | Reserved for Eventbrite events |

Digest recipients live in `digest_recipients.txt` (one email per line), not in `.env`.

`.env`, `database_ids.json`, `runs.log`, and the `seen_*.json` dedup caches are all gitignored.

---

## Scrapers

Each scraper is standalone and can be run on its own:

```bash
python scrapers/news_scraper.py
python scrapers/restaurants_scraper.py
python scrapers/sos_scraper.py
python scrapers/events_scraper.py
python scrapers/development_scraper.py
python scrapers/digest.py           # add --debug to send only to yourself
```

| Scraper | Sources | Notion target | Dedup cache |
|---|---|---|---|
| [news_scraper.py](scrapers/news_scraper.py) | westervilleoh.io, Google News RSS, NBC4, 10TV — 90-day cutoff, obit/sports/real-estate filters | 📰 Local News | `seen_news_urls.json` |
| [restaurants_scraper.py](scrapers/restaurants_scraper.py) | Google Places API (New), 8km radius around 40.1262, -82.9291 | 🍽️ Restaurants & Businesses | `seen_place_ids.json` |
| [sos_scraper.py](scrapers/sos_scraper.py) | Ohio Secretary of State business search (ZIPs 43081, 43082), active filings from last 90 days | 🍽️ Restaurants & Businesses (Status = "New Filing") | `seen_sos_entities.json` |
| [events_scraper.py](scrapers/events_scraper.py) | Visit Westerville Tribe Events API, westerville.org + parks.westerville.org (CivicPlus) — next 30 days | 🎉 Events & Happenings | `seen_event_urls.json` |
| [development_scraper.py](scrapers/development_scraper.py) | Google News RSS (construction/planning/infrastructure), westervilleoh.io, Columbus Underground | 🏗️ Development & Projects | `seen_development_urls.json` |
| [digest.py](scrapers/digest.py) | Reads the last 24h back out of Notion | — sends email | — |

Supporting modules: [utils.py](scrapers/utils.py) (shared helpers) and
[holiday_utils.py](scrapers/holiday_utils.py) (holiday-themed digest greetings).

Delete a `seen_*.json` file to reset that scraper's cache and re-pull everything.

---

## Notion databases

`setup_notion.py` creates four databases and writes their IDs to `database_ids.json`:

| Database | Key fields |
|---|---|
| 📰 Local News | Title, Source, Category, Published Date, URL, Summary |
| 🍽️ Restaurants & Businesses | Name, Type, Cuisine, Address, Neighborhood, Rating, Status |
| 🎉 Events & Happenings | Event Name, Category, Start Date, Location, Is Free, Source |
| 🏗️ Development & Projects | Project Name, Type, Status, Location, Est. Completion |

---

## Web app

### Backend — [backend/](backend/)

FastAPI proxy over the Notion databases with a 15-minute in-memory cache. The Notion
token stays server-side and is never exposed to the browser.

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload      # http://localhost:8000
```

Endpoints: `/health`, `/api/news`, `/api/restaurants`, `/api/events`, `/api/development`.

CORS currently allows all origins — tighten `allow_origins` in
[main.py](backend/main.py#L47) before deploying.

### Frontend — [frontend/](frontend/)

React 19 + Vite + Tailwind v4.

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

Set `VITE_API_URL` to point at a deployed backend; it defaults to `http://localhost:8000`.

---

## Automation

[.github/workflows/scrape.yml](.github/workflows/scrape.yml) runs `run_all.py` daily at
11:00 UTC (7am EDT) and can be triggered manually from the Actions tab. Dedup caches are
persisted between runs with `actions/cache`, and `runs.log` is uploaded as an artifact
(30-day retention).

Required repository secrets: `NOTION_TOKEN`, `NOTION_PARENT_PAGE_ID`, `GOOGLE_API_KEY`,
`EVENTBRITE_API_KEY`, `ANTHROPIC_API_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, and
`DATABASE_IDS_JSON` (the contents of your local `database_ids.json`).

---

## Gotchas

- Google Places API (New) renamed its fields — `id` not `place_id`, `displayName.text` not `name`, `formattedAddress` not `vicinity`.
- The Notion API rejects `null` URL fields; always check before setting one.
- Google News RSS caps out at 100 results per query.
- `westerville.org` returns 403 for automated requests, so Planning Commission pages aren't directly scrapeable — Google News picks those stories up once they hit the press.
- The Ohio SOS scraper exits cleanly (code 0) with a ⚠️ warning if it gets bot-blocked, so it never breaks `run_all.py`. If it stays blocked, Playwright-based browser scraping is the next step.

---

## Docs

- [CLAUDE.md](CLAUDE.md) — project context and conventions for Claude Code
- [DATA_SOURCES.md](DATA_SOURCES.md) — notes on candidate and in-use data sources

## License

[MIT](LICENSE) © Eric Schneider
