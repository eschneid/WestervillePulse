"""
WestervillePulse — Daily Email Digest
======================================
Queries Notion for content added/upcoming in the last 24 hours,
uses Claude Haiku to write a friendly intro, then sends an HTML
email via Gmail SMTP.

Requires in .env:
    NOTION_TOKEN, GMAIL_USER, GMAIL_APP_PASSWORD, DIGEST_TO
    ANTHROPIC_API_KEY  (optional — falls back to plain intro)

Usage:
    python scrapers/digest.py
"""

import os
import sys
import json
import smtplib
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import elapsed, find_db_ids_path, load_dotenv_files

load_dotenv_files(__file__)

# ── Config ────────────────────────────────────────────────────────────────────

NOTION_TOKEN      = os.getenv("NOTION_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GMAIL_USER        = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD= os.getenv("GMAIL_APP_PASSWORD", "")
DIGEST_TO_RAW     = os.getenv("DIGEST_TO", "")

NOTION_BASE    = "https://api.notion.com/v1"
NOTION_HEADERS = {
    "Authorization":  f"Bearer {NOTION_TOKEN}",
    "Content-Type":   "application/json",
    "Notion-Version": "2022-06-28",
}

DB_IDS_PATH = find_db_ids_path(__file__)

TODAY     = datetime.now(timezone.utc).date()
YESTERDAY = TODAY - timedelta(days=1)
WEEK_OUT  = TODAY + timedelta(days=7)

_HOUR_ET     = datetime.now(ZoneInfo("America/New_York")).hour
TIME_OF_DAY  = "morning" if _HOUR_ET < 12 else "afternoon" if _HOUR_ET < 17 else "evening"


def _fmt_full_date(d) -> str:
    """Format a date as 'Monday, March 2, 2026' — cross-platform (no %-d)."""
    return f"{d.strftime('%A, %B')} {d.day}, {d.year}"


def _fmt_short_date(d) -> str:
    """Format a date as 'Mon Mar 2' — cross-platform."""
    return f"{d.strftime('%a %b')} {d.day}"


# ── Notion helpers ────────────────────────────────────────────────────────────

def _load_db_ids() -> dict:
    if not DB_IDS_PATH.exists():
        print("  ❌  database_ids.json not found.")
        sys.exit(1)
    with open(DB_IDS_PATH) as f:
        return json.load(f)


def _query(db_id: str, body: dict) -> list[dict]:
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
            print(f"  ⚠️  Notion query failed ({resp.status_code}): {resp.text[:200]}")
            return []
        data = resp.json()
        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        body["start_cursor"] = data["next_cursor"]
    return pages


def _text(prop) -> str:
    if not prop:
        return ""
    items = prop.get("title") or prop.get("rich_text") or []
    return "".join(t.get("plain_text", "") for t in items)

def _select(prop) -> str:
    if not prop:
        return ""
    return (prop.get("select") or {}).get("name", "")

def _multi(prop) -> list[str]:
    if not prop:
        return []
    return [o["name"] for o in prop.get("multi_select", [])]

def _date(prop) -> str | None:
    if not prop:
        return None
    return (prop.get("date") or {}).get("start")

def _url(prop) -> str | None:
    if not prop:
        return None
    return prop.get("url") or None

def _bool(prop) -> bool:
    return bool((prop or {}).get("checkbox", False))


# ── Weather ────────────────────────────────────────────────────────────────────

_WMO_CODES = {
    0:  ("☀️",  "Clear"),
    1:  ("🌤️", "Mostly Clear"),
    2:  ("⛅",  "Partly Cloudy"),
    3:  ("☁️",  "Overcast"),
    45: ("🌫️", "Foggy"),
    48: ("🌫️", "Foggy"),
    51: ("🌦️", "Light Drizzle"),
    53: ("🌦️", "Drizzle"),
    55: ("🌧️", "Heavy Drizzle"),
    61: ("🌧️", "Light Rain"),
    63: ("🌧️", "Rain"),
    65: ("🌧️", "Heavy Rain"),
    71: ("🌨️", "Light Snow"),
    73: ("🌨️", "Snow"),
    75: ("❄️",  "Heavy Snow"),
    77: ("🌨️", "Snow Grains"),
    80: ("🌦️", "Rain Showers"),
    81: ("🌧️", "Rain Showers"),
    82: ("⛈️",  "Heavy Showers"),
    85: ("🌨️", "Snow Showers"),
    86: ("❄️",  "Heavy Snow"),
    95: ("⛈️",  "Thunderstorm"),
    96: ("⛈️",  "Thunderstorm"),
    99: ("⛈️",  "Thunderstorm"),
}


def _wmo(code: int) -> tuple[str, str]:
    return _WMO_CODES.get(code, ("🌡️", "Unknown"))


def fetch_weather() -> list[dict] | None:
    """Fetch a 4-day forecast from Open-Meteo (free, no API key required)."""
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude":   40.1262,
                "longitude":  -82.9291,
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "temperature_unit": "fahrenheit",
                "timezone":   "America/New_York",
                "forecast_days": 4,
            },
            timeout=10,
        )
        if not resp.ok:
            print(f"  ⚠️  Weather fetch failed ({resp.status_code})")
            return None
        data = resp.json()["daily"]
        days = []
        for i in range(len(data["time"])):
            emoji, desc = _wmo(data["weather_code"][i])
            days.append({
                "date":   data["time"][i],
                "emoji":  emoji,
                "desc":   desc,
                "high":   round(data["temperature_2m_max"][i]),
                "low":    round(data["temperature_2m_min"][i]),
                "precip": data["precipitation_probability_max"][i],
            })
        return days
    except Exception as e:
        print(f"  ⚠️  Weather error: {e}")
        return None


def _weather_html(weather: list[dict]) -> str:
    if not weather:
        return ""
    cells = ""
    for i, w in enumerate(weather):
        if i > 0:
            cells += '<td width="5"></td>'
        if i == 0:
            label      = "TODAY"
            label_col  = "#1e40af"
            bg         = "#ffffff"
            emoji_size = "26px"
            temp_size  = "20px"
        else:
            d          = datetime.fromisoformat(w["date"])
            label      = _fmt_short_date(d).upper()
            label_col  = "#6b7280"
            bg         = "#dbeafe"
            emoji_size = "18px"
            temp_size  = "13px"
        precip = f" · {w['precip']}% 🌧" if w["precip"] >= 20 else ""
        cells += (
            f'<td align="center" valign="top" '
            f'style="background:{bg};border-radius:8px;padding:12px 6px;">'
            f'<div style="font-size:{emoji_size};">{w["emoji"]}</div>'
            f'<div style="font-size:10px;font-weight:700;color:{label_col};'
            f'margin:4px 0 2px;white-space:nowrap;">{label}</div>'
            f'<div style="font-size:{temp_size};font-weight:700;color:#111827;">{w["high"]}°</div>'
            f'<div style="font-size:11px;color:#9ca3af;">/{w["low"]}°F</div>'
            f'<div style="font-size:10px;color:#6b7280;margin-top:3px;">{w["desc"]}{precip}</div>'
            f'</td>'
        )
    return (
        '<div style="background:#eff6ff;border-radius:10px;padding:14px 16px;margin:16px 0 20px;">'
        '<p style="margin:0 0 10px;font-size:11px;font-weight:700;color:#3b82f6;letter-spacing:.08em;">'
        '⛅ WESTERVILLE WEATHER</p>'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
        f'<tr>{cells}</tr>'
        '</table></div>'
    )


# ── Fetch each section ────────────────────────────────────────────────────────

def fetch_news(db_id: str) -> list[dict]:
    pages = _query(db_id, {
        "filter": {"property": "Scraped At", "date": {"on_or_after": YESTERDAY.isoformat()}},
        "sorts":  [{"property": "Published Date", "direction": "descending"}],
    })
    return [
        {
            "title":  _text(p["properties"].get("Title")),
            "source": _select(p["properties"].get("Source")),
            "url":    _url(p["properties"].get("URL")),
        }
        for p in pages if _text(p["properties"].get("Title"))
    ]


def fetch_events(db_id: str) -> list[dict]:
    pages = _query(db_id, {
        "filter": {
            "and": [
                {"property": "Start Date", "date": {"on_or_after": TODAY.isoformat()}},
                {"property": "Start Date", "date": {"on_or_before": WEEK_OUT.isoformat()}},
            ]
        },
        "sorts": [{"property": "Start Date", "direction": "ascending"}],
    })
    seen, result = set(), []
    for p in pages:
        name = _text(p["properties"].get("Event Name"))
        if not name:
            continue
        start_date = _date(p["properties"].get("Start Date"))
        key = (name, start_date)
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "name":       name,
            "start_date": start_date,
            "location":   _text(p["properties"].get("Location / Venue")),
            "is_free":    _bool(p["properties"].get("Is Free")),
            "url":        _url(p["properties"].get("Event URL")),
        })
    return result


def fetch_restaurants(db_id: str) -> list[dict]:
    pages = _query(db_id, {
        "filter": {"property": "Discovered At", "date": {"on_or_after": YESTERDAY.isoformat()}},
        "sorts":  [{"property": "Discovered At", "direction": "descending"}],
    })
    return [
        {
            "name":         _text(p["properties"].get("Name")),
            "type":         _select(p["properties"].get("Type")),
            "neighborhood": _select(p["properties"].get("Neighborhood")),
            "website":      _url(p["properties"].get("Website")),
        }
        for p in pages if _text(p["properties"].get("Name"))
    ]


def fetch_development(db_id: str) -> list[dict]:
    pages = _query(db_id, {
        "filter": {"property": "Discovered At", "date": {"on_or_after": YESTERDAY.isoformat()}},
        "sorts":  [{"property": "Discovered At", "direction": "descending"}],
    })
    return [
        {
            "name":       _text(p["properties"].get("Project Name")),
            "status":     _select(p["properties"].get("Status")),
            "location":   _text(p["properties"].get("Location")),
            "source_url": _url(p["properties"].get("Source URL")),
        }
        for p in pages if _text(p["properties"].get("Project Name"))
    ]


# ── Claude intro ──────────────────────────────────────────────────────────────

def generate_intro(n_news, n_events, n_restaurants, n_dev, weather=None) -> str:
    fallback = (
        f"Here's your daily Westerville update for "
        f"{_fmt_full_date(TODAY)}. "
        f"Check out what's happening in your community below."
    )
    if not ANTHROPIC_API_KEY:
        return fallback
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        weather_ctx = ""
        if weather:
            w = weather[0]
            weather_ctx = (
                f" Today's weather: {w['desc']}, high {w['high']}°F / low {w['low']}°F"
                + (f", {w['precip']}% chance of precipitation" if w["precip"] >= 30 else "")
                + "."
            )
        prompt = (
            f"Write a friendly 2-3 sentence intro for a daily Westerville, OH neighborhood "
            f"newsletter. Today is {_fmt_full_date(TODAY)}.{weather_ctx} "
            f"There are {n_news} new local news articles, {n_events} events coming up this "
            f"week, {n_restaurants} new businesses discovered, and {n_dev} development updates. "
            f"Start with 'Good {TIME_OF_DAY.capitalize()}, Westerville!'. "
            f"Keep it warm, civic-minded, and specific to Westerville. "
            f"Plain text only — no markdown, no hashtags, no bullet points."
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        # Strip any markdown heading markers Claude might still add
        text = text.lstrip("#").strip()
        return text
    except Exception as e:
        print(f"  ⚠️  Claude intro error: {e}")
        return fallback


# ── Email builders ────────────────────────────────────────────────────────────

def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "TBD"
    try:
        d = datetime.fromisoformat(iso.split("T")[0])
        return _fmt_short_date(d)
    except Exception:
        return iso


def build_plain(intro: str, news, events, restaurants, development, weather=None) -> str:
    lines = [
        f"WESTERVILLE PULSE — {_fmt_full_date(TODAY)}",
        "=" * 55,
        "",
        intro,
        "",
    ]

    if weather:
        lines += ["WEATHER (Westerville, OH)", "-" * 30]
        for i, w in enumerate(weather):
            label = "Today" if i == 0 else _fmt_short_date(datetime.fromisoformat(w["date"]))
            precip = f", {w['precip']}% rain" if w["precip"] >= 20 else ""
            lines.append(f"• {label}: {w['emoji']} {w['desc']}, {w['high']}°/{w['low']}°F{precip}")
        lines.append("")

    if news:
        lines += [f"NEWS ({len(news)} articles)", "-" * 30]
        for a in news:
            lines.append(f"• {a['title']} — {a['source']}")
            if a["url"]:
                lines.append(f"  {a['url']}")
        lines.append("")

    if events:
        lines += [f"THIS WEEK'S EVENTS ({len(events)})", "-" * 30]
        for e in events:
            free = " [FREE]" if e["is_free"] else ""
            loc  = f" @ {e['location']}" if e["location"] else ""
            lines.append(f"• {_fmt_date(e['start_date'])} — {e['name']}{loc}{free}")
            if e["url"]:
                lines.append(f"  {e['url']}")
        lines.append("")

    if restaurants:
        lines += [f"NEW BUSINESSES ({len(restaurants)})", "-" * 30]
        for r in restaurants:
            parts = [r["name"]]
            if r["type"]:         parts.append(r["type"])
            if r["neighborhood"]: parts.append(r["neighborhood"])
            lines.append(f"• {' — '.join(parts)}")
        lines.append("")

    if development:
        lines += [f"DEVELOPMENT UPDATES ({len(development)})", "-" * 30]
        for d in development:
            parts = [d["name"]]
            if d["status"]:   parts.append(d["status"])
            if d["location"]: parts.append(d["location"])
            lines.append(f"• {' — '.join(parts)}")
            if d["source_url"]:
                lines.append(f"  {d['source_url']}")
        lines.append("")

    lines += ["---", "Westerville Pulse • Reply to unsubscribe"]
    return "\n".join(lines)


def build_html(intro: str, news, events, restaurants, development, weather=None) -> str:
    date_str = _fmt_full_date(TODAY)

    def section(emoji, title, items_html):
        if not items_html:
            return ""
        return f"""
        <div style="margin:28px 0;">
          <h2 style="font-size:16px;font-weight:700;color:#1a1a2e;margin:0 0 12px;
                     border-bottom:2px solid #e5e7eb;padding-bottom:8px;">
            {emoji} {title}
          </h2>
          <ul style="margin:0;padding:0;list-style:none;">{items_html}</ul>
        </div>"""

    def li(content):
        return f'<li style="padding:6px 0;border-bottom:1px solid #f3f4f6;font-size:14px;color:#374151;">{content}</li>'

    def link(text, url):
        if not url:
            return f"<strong>{text}</strong>"
        return f'<a href="{url}" style="color:#2563eb;text-decoration:none;font-weight:600;">{text}</a>'

    def badge(text, color="#d1fae5", tc="#065f46"):
        return f'<span style="background:{color};color:{tc};font-size:11px;font-weight:600;padding:2px 6px;border-radius:9999px;margin-left:6px;">{text}</span>'

    news_items = "".join(
        li(f"{link(a['title'], a['url'])} {badge(a['source'], '#dbeafe', '#1e40af')}")
        for a in news
    )
    event_items = "".join(
        li(
            f'<span style="color:#6b7280;min-width:80px;display:inline-block;">{_fmt_date(e["start_date"])}</span>'
            f"{link(e['name'], e['url'])}"
            + (f" <em style='color:#6b7280;font-size:12px;'>@ {e['location']}</em>" if e["location"] else "")
            + (badge("FREE") if e["is_free"] else "")
        )
        for e in events
    )
    rest_items = "".join(
        li(
            f"{link(r['name'], r['website'])}"
            + (f" {badge(r['type'], '#fef3c7', '#92400e')}" if r["type"] else "")
            + (f" <em style='color:#9ca3af;font-size:12px;'>{r['neighborhood']}</em>" if r["neighborhood"] else "")
        )
        for r in restaurants
    )
    dev_items = "".join(
        li(
            f"{link(d['name'], d['source_url'])}"
            + (f" {badge(d['status'], '#e0e7ff', '#3730a3')}" if d["status"] else "")
            + (f" <em style='color:#9ca3af;font-size:12px;'>{d['location']}</em>" if d["location"] else "")
        )
        for d in development
    )

    body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:600px;margin:24px auto;background:#fff;border-radius:12px;
              box-shadow:0 1px 3px rgba(0,0,0,.1);overflow:hidden;">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);padding:28px 32px;">
      <div style="font-size:28px;margin-bottom:4px;">🌆</div>
      <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;letter-spacing:-0.5px;">
        Westerville Pulse
      </h1>
      <p style="margin:4px 0 0;color:#94a3b8;font-size:13px;">{date_str}</p>
    </div>

    <!-- Content -->
    <div style="padding:24px 32px;">
      <p style="font-size:15px;color:#374151;line-height:1.6;margin:0 0 8px;">{intro}</p>

      {_weather_html(weather)}

      {section("📰", f"Today's News &nbsp;<span style='font-weight:400;color:#6b7280;'>({len(news)})</span>", news_items)}
      {section("🎉", f"This Week's Events &nbsp;<span style='font-weight:400;color:#6b7280;'>({len(events)})</span>", event_items)}
      {section("🍽️", f"New Businesses &nbsp;<span style='font-weight:400;color:#6b7280;'>({len(restaurants)})</span>", rest_items)}
      {section("🏗️", f"Development Updates &nbsp;<span style='font-weight:400;color:#6b7280;'>({len(development)})</span>", dev_items)}
    </div>

    <!-- Footer -->
    <div style="background:#f3f4f6;padding:16px 32px;text-align:center;">
      <p style="margin:0;font-size:12px;color:#9ca3af;">
        Westerville Pulse • Automated daily digest &nbsp;|&nbsp; Reply to unsubscribe
      </p>
    </div>
  </div>
</body></html>"""
    return body


# ── Send ──────────────────────────────────────────────────────────────────────

def send_email(subject: str, plain: str, html: str, recipients: list[str]) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html,  "html",  "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_USER, recipients, msg.as_string())
        return True
    except Exception as e:
        print(f"  ⚠️  Email send failed: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print()
    print("WestervillePulse -- Daily Email Digest")
    print("=" * 55)

    # Check required env vars
    missing = [v for v in ("NOTION_TOKEN", "GMAIL_USER", "GMAIL_APP_PASSWORD", "DIGEST_TO") if not os.getenv(v)]
    if missing:
        print(f"\n  ⚠️  Missing env vars: {', '.join(missing)} — skipping digest.")
        print("  Added 0 digest\n")
        return

    recipients = [r.strip() for r in DIGEST_TO_RAW.split(",") if r.strip()]
    if not recipients:
        print("  ⚠️  DIGEST_TO is empty — skipping digest.")
        print("  Added 0 digest\n")
        return

    total_start = time.time()
    db_ids = _load_db_ids()

    # Fetch weather
    t = time.time()
    print(f"  Fetching: {'Weather':<30}", end="", flush=True)
    weather = fetch_weather()
    print(f"  {'OK' if weather else 'unavailable'}  ({elapsed(t)})")

    # Fetch all sections
    t = time.time()
    print(f"  Fetching: {'News':<30}", end="", flush=True)
    news = fetch_news(db_ids.get("news_database_id", ""))
    print(f"  {len(news)} items  ({elapsed(t)})")

    t = time.time()
    print(f"  Fetching: {'Events (next 7 days)':<30}", end="", flush=True)
    events = fetch_events(db_ids.get("events_database_id", ""))
    print(f"  {len(events)} items  ({elapsed(t)})")

    t = time.time()
    print(f"  Fetching: {'New Businesses':<30}", end="", flush=True)
    restaurants = fetch_restaurants(db_ids.get("restaurants_database_id", ""))
    print(f"  {len(restaurants)} items  ({elapsed(t)})")

    t = time.time()
    print(f"  Fetching: {'Development':<30}", end="", flush=True)
    development = fetch_development(db_ids.get("development_database_id", ""))
    print(f"  {len(development)} items  ({elapsed(t)})")

    total_items = len(news) + len(events) + len(restaurants) + len(development)
    if total_items == 0:
        print("\n  Nothing new today — skipping digest email.")
        print("  Added 0 digest\n")
        return

    # Generate Claude intro
    t = time.time()
    print(f"\n  Generating intro...", end="", flush=True)
    intro = generate_intro(len(news), len(events), len(restaurants), len(development), weather)
    print(f"  ({elapsed(t)})")
    print(f"  → {intro[:80]}...")

    # Build and send email
    date_str = f"{TODAY.strftime('%A, %B')} {TODAY.day}"
    subject  = f"🌆 Westerville Pulse — {date_str}"
    plain    = build_plain(intro, news, events, restaurants, development, weather)
    html     = build_html(intro, news, events, restaurants, development, weather)

    print(f"\n  Sending to: {', '.join(recipients)}")
    t = time.time()
    success = send_email(subject, plain, html, recipients)

    print()
    print("=" * 55)
    if success:
        print(f"  Digest sent! ({len(recipients)} recipient(s))")
        print(f"  Added 1 digest")
    else:
        print("  Digest failed — check output above.")
        print("  Added 0 digest")
    print(f"  Total runtime: {elapsed(total_start)}")
    print()


if __name__ == "__main__":
    run()
