# 🌆 WestervillePulse — Data Sources & Scraping Strategy

## 📡 Recommended Data Sources

### 📰 Local News
| Source | Method | URL |
|---|---|---|
| ThisWeek Community News | RSS Feed / Scrape | https://www.thisweeknews.com/search/?q=westerville |
| Columbus Dispatch | RSS Feed | https://www.dispatch.com |
| 10TV / NBC4 Columbus | RSS Feed | https://www.10tv.com |
| City of Westerville Official Site | Scrape / Press Releases | https://www.westerville.org |
| Westerville Schools | Scrape | https://www.wcsoh.org |

**Approach:**
- Use `feedparser` library for RSS feeds
- Use `requests` + `BeautifulSoup` for sites without RSS
- Filter results by keyword: "Westerville"

---

### 🍽️ New Restaurants & Businesses
| Source | Method | Notes |
|---|---|---|
| Google Places API | API | Search "new restaurants Westerville OH" — returns ratings, hours, address |
| Yelp Fusion API | API | Filter by date listed, category, location |
| Ohio Secretary of State | Scrape | New business filings in Westerville ZIP codes |
| Westerville Area Chamber | Scrape | https://www.westervillechamber.com/member-directory |

**Approach:**
- Google Places API: use `nearbysearch` with `type=restaurant` and rank by `newest`
- Yelp: use `/businesses/search` endpoint filtered by zip code 43081, 43082
- Cross-reference both sources to deduplicate

---

### 🎉 Events & Happenings
| Source | Method | URL |
|---|---|---|
| Westerville Parks & Rec | Scrape | https://www.westerville.org/recreation |
| City Calendar | Scrape / iCal | https://www.westerville.org/calendar |
| Eventbrite | API | `eventbrite.com/api/v3/events/search/?location.address=Westerville,OH` |
| Facebook Events | Graph API or Scrape | Search "Westerville" public events |
| Columbus Alive | Scrape | https://www.columbusalive.com/events/ |

**Approach:**
- Eventbrite has a clean free API — best starting point
- City calendar often has iCal exports (`.ics` files) — use `icalendar` Python library
- BeautifulSoup scrape for Parks & Rec page

---

### 🏗️ Development & City Projects
| Source | Method | URL |
|---|---|---|
| Westerville Planning & Zoning | Scrape | https://www.westerville.org/government/departments/planning-zoning |
| Franklin County Auditor | API / Scrape | Property permits and new builds |
| City Council Agendas | Scrape / PDF parse | Meeting minutes often list approved developments |

**Approach:**
- Parse City Council PDF meeting minutes using `pdfplumber` or `PyMuPDF`
- Monitor planning board agenda pages for new filings

---

## 🛠️ Python Libraries You'll Need

```
pip install requests beautifulsoup4 feedparser icalendar notion-client python-dotenv pdfplumber lxml
```

---

## 🗓️ Suggested Run Schedule (cron)

```
# Run news scraper daily at 7am
0 7 * * * python scrapers/news_scraper.py

# Run events scraper daily at 8am
0 8 * * * python scrapers/events_scraper.py

# Run restaurants/businesses weekly on Mondays
0 9 * * 1 python scrapers/restaurants_scraper.py

# Run city development scraper weekly on Wednesdays
0 9 * * 3 python scrapers/development_scraper.py
```

---

## 🔑 API Keys You'll Need

| Service | Where to Get |
|---|---|
| Notion Integration Token | https://www.notion.so/my-integrations |
| Google Places API | https://console.cloud.google.com → Maps API |
| Yelp Fusion API | https://www.yelp.com/developers |
| Eventbrite API | https://www.eventbrite.com/platform |

---

## 📁 Suggested Project Structure

```
westerville_pulse/
├── setup_notion.py          ← Run once to create Notion databases
├── database_ids.json        ← Auto-generated after setup
├── .env                     ← API keys (never commit this!)
├── DATA_SOURCES.md          ← This file
├── scrapers/
│   ├── news_scraper.py
│   ├── events_scraper.py
│   ├── restaurants_scraper.py
│   └── development_scraper.py
├── notion/
│   └── notion_client.py     ← Shared Notion write helpers
└── utils/
    └── deduplication.py     ← Prevent duplicate entries
```
