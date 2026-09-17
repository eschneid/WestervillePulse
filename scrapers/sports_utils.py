"""
WestervillePulse — Local Sports Snippet
========================================
Pulls recent results and upcoming games for the local pro/college teams
from ESPN's public site API (free, no key, but undocumented — may change).

A team shows up in the digest only when a game is nearby:
    - a result from the last RESULT_DAYS days
    - a preview for a game within PREVIEW_DAYS days (labeled TODAY on game day)
Teams with nothing nearby are omitted; if no team qualifies, the section is hidden.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
ET        = ZoneInfo("America/New_York")

PREVIEW_DAYS = 3
RESULT_DAYS  = 2

TEAMS = [
    {"name": "Ohio State",  "emoji": "🏈", "path": "football/college-football", "id": "194", "color": "#bb0000"},
    {"name": "Bengals",     "emoji": "🏈", "path": "football/nfl",              "id": "4",   "color": "#fb4f14"},
    {"name": "Browns",      "emoji": "🏈", "path": "football/nfl",              "id": "5",   "color": "#311d00"},
    # MLS schedule only returns played games; upcoming ones need fixture=true
    {"name": "Columbus Crew", "emoji": "⚽", "path": "soccer/usa.1",            "id": "183", "color": "#fedd00",
     "fixtures": True},
]


def _get(url: str, params: dict | None = None) -> dict:
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _score(competitor: dict) -> str:
    s = competitor.get("score")
    if isinstance(s, dict):
        return s.get("displayValue", "")
    return str(s or "")


def _opponent_label(comp: dict, us: dict, them: dict) -> str:
    """'vs. Kent State', 'at No. 4 Texas' — ranks shown only for the Top 25."""
    rank = (them.get("curatedRank") or {}).get("current", 99)
    name = them["team"].get("shortDisplayName") or them["team"].get("displayName", "")
    if rank and rank <= 25:
        name = f"No. {rank} {name}"
    where = "at" if us.get("homeAway") == "away" and not comp.get("neutralSite") else "vs."
    return f"{where} {name}"


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def _parse_game(ev: dict, team_id: str, today) -> dict | None:
    comp = (ev.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []
    us   = next((c for c in competitors if c.get("id") == team_id), None)
    them = next((c for c in competitors if c.get("id") != team_id), None)
    if not us or not them:
        return None

    status = (comp.get("status") or {}).get("type") or {}
    start  = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(ET)
    days   = (start.date() - today).days
    opp    = _opponent_label(comp, us, them)

    if status.get("completed"):
        if not -RESULT_DAYS <= days <= 0:
            return None
        if us.get("winner"):
            outcome = "W"
        elif them.get("winner"):
            outcome = "L"
        else:
            outcome = "D"
        return {
            "kind":    "result",
            "start":   start,
            "outcome": outcome,
            "text":    f"{outcome} {_score(us)}-{_score(them)} {opp} ({start.strftime('%a')})",
        }

    # Skip postponed/canceled games, which ESPN marks "post" without completing
    if status.get("state") != "pre" or not 0 <= days <= PREVIEW_DAYS:
        return None
    day = "Today" if days == 0 else "Tomorrow" if days == 1 else start.strftime("%a")
    tbd = not ev.get("timeValid", True) or "TBD" in status.get("shortDetail", "")
    when = f"{day}, time TBD" if tbd else f"{day} {_fmt_time(start)}"
    tv = next((b.get("media", {}).get("shortName") for b in comp.get("broadcasts") or []
               if b.get("media", {}).get("shortName")), None)
    return {
        "kind":     "preview",
        "start":    start,
        "is_today": days == 0,
        "text":     f"{when} {opp}" + (f" · {tv}" if tv else ""),
    }


def _fetch_team(team: dict, today) -> dict | None:
    url = f"{ESPN_BASE}/{team['path']}/teams/{team['id']}"
    events = {ev["id"]: ev for ev in _get(f"{url}/schedule").get("events", [])}
    if team.get("fixtures"):
        events.update({ev["id"]: ev for ev in _get(f"{url}/schedule", {"fixture": "true"}).get("events", [])})

    games = [g for g in (_parse_game(ev, team["id"], today) for ev in events.values()) if g]
    results  = sorted((g for g in games if g["kind"] == "result"),  key=lambda g: g["start"])
    previews = sorted((g for g in games if g["kind"] == "preview"), key=lambda g: g["start"])
    if not results and not previews:
        return None

    items = (_get(url).get("team", {}).get("record") or {}).get("items") or []
    total = next((i for i in items if i.get("type") == "total"), {})
    record = total.get("summary", "")
    stats = {s.get("name"): int(s.get("value", 0)) for s in total.get("stats") or []}
    if team["path"].startswith("soccer") and stats:
        # ESPN's soccer summary is W-D-L, which reads like W-L-D to US readers
        record = f"{stats.get('wins', 0)}W {stats.get('losses', 0)}L {stats.get('ties', 0)}D"
    return {
        "name":   team["name"],
        "emoji":  team["emoji"],
        "color":  team["color"],
        "record": record,
        "result": results[-1] if results else None,
        "next":   previews[0] if previews else None,
    }


def fetch_sports() -> list[dict]:
    """Return one entry per team with a nearby game. Failures skip that team only."""
    today = datetime.now(ET).date()
    out = []
    for team in TEAMS:
        try:
            entry = _fetch_team(team, today)
            if entry:
                out.append(entry)
        except Exception as e:
            print(f"\n  ⚠️  Sports fetch failed for {team['name']}: {e}", end="")
    return out


if __name__ == "__main__":
    for s in fetch_sports():
        print(f"{s['emoji']} {s['name']} ({s['record']})")
        if s["result"]:
            print(f"   Final: {s['result']['text']}")
        if s["next"]:
            print(f"   {'TODAY' if s['next']['is_today'] else 'Next'}: {s['next']['text']}")
