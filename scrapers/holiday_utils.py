"""
WestervillePulse — Holiday Awareness Utilities
================================================
Detects today's holiday (official US or fun/unofficial) and returns
a name, emoji, and themed greeting for use in the daily email digest.

Reusable across the project:
    from holiday_utils import get_today_holiday, get_holiday_greeting, filter_holiday_events

Requires the `holidays` library (pip install holidays) for official US holidays.
Falls back gracefully to the hardcoded unofficial dict if the library is missing.
"""

import datetime

try:
    import holidays as _holidays_lib
    _HAS_HOLIDAYS_LIB = True
except ImportError:
    _HAS_HOLIDAYS_LIB = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _super_bowl_sunday(year: int) -> datetime.date:
    """Return the Super Bowl date (approximated as the second Sunday in February)."""
    d = datetime.date(year, 2, 1)
    while d.weekday() != 6:   # advance to first Sunday
        d += datetime.timedelta(days=1)
    return d + datetime.timedelta(weeks=1)  # second Sunday


def _easter_sunday(year: int) -> datetime.date:
    """Compute Easter Sunday (Anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(114 + h + l - 7 * m, 31)
    return datetime.date(year, month, day + 1)


# ── Unofficial / fun holidays ─────────────────────────────────────────────────

def _unofficial_holidays(year: int) -> dict[datetime.date, tuple[str, str]]:
    """
    Hardcoded dict of fun/unofficial holidays not covered by the `holidays` library.
    Maps date -> (holiday_name, emoji).
    Computed dates (Super Bowl, Easter) are recalculated per year.
    """
    return {
        datetime.date(year, 1, 1):   ("New Year's Day",       "🎆"),
        datetime.date(year, 2, 14):  ("Valentine's Day",      "💝"),
        _super_bowl_sunday(year):    ("Super Bowl Sunday",    "🏈"),
        _easter_sunday(year):        ("Easter Sunday",        "🐣"),
        datetime.date(year, 3, 17):  ("St. Patrick's Day",    "🍀"),
        datetime.date(year, 4, 1):   ("April Fools' Day",     "🃏"),
        datetime.date(year, 5, 4):   ("Star Wars Day",        "⭐"),
        datetime.date(year, 5, 5):   ("Cinco de Mayo",        "🌮"),
        datetime.date(year, 6, 19):  ("Juneteenth",           "✊"),
        datetime.date(year, 7, 4):   ("Independence Day",     "🎇"),
        datetime.date(year, 10, 31): ("Halloween",            "🎃"),
        datetime.date(year, 11, 11): ("Veterans Day",         "🎖️"),
        datetime.date(year, 12, 24): ("Christmas Eve",        "🎁"),
        datetime.date(year, 12, 25): ("Christmas Day",        "🎄"),
        datetime.date(year, 12, 31): ("New Year's Eve",       "🥂"),
    }


# ── Official holiday emoji map ────────────────────────────────────────────────

_OFFICIAL_EMOJI: dict[str, str] = {
    "new year's day":                        "🎆",
    "martin luther king":                    "✊",
    "washington's birthday":                 "🇺🇸",
    "presidents":                            "🇺🇸",
    "memorial day":                          "🎖️",
    "juneteenth":                            "✊",
    "independence day":                      "🎇",
    "labor day":                             "⚒️",
    "columbus day":                          "⚓",
    "indigenous peoples":                    "🌎",
    "veterans day":                          "🎖️",
    "thanksgiving":                          "🦃",
    "christmas":                             "🎄",
}


def _emoji_for_official(name: str) -> str:
    name_lc = name.lower()
    for keyword, emoji in _OFFICIAL_EMOJI.items():
        if keyword in name_lc:
            return emoji
    return "🎉"


# ── Greetings ─────────────────────────────────────────────────────────────────

_GREETINGS: dict[str, str] = {
    "New Year's Day":                    "Kicking off the new year right here in Westerville!",
    "Martin Luther King Jr. Day":        "Honoring Dr. King's legacy and keeping his dream alive in Westerville.",
    "Valentine's Day":                   "Spreading a little love across Westerville today!",
    "Super Bowl Sunday":                 "It's game day, Westerville — find your squad and enjoy the big game!",
    "Easter Sunday":                     "Wishing Westerville a joyful Easter Sunday!",
    "St. Patrick's Day":                 "The luck of the Irish is with Westerville today!",
    "April Fools' Day":                  "No fooling — there's real news happening in Westerville today!",
    "Star Wars Day":                     "May the 4th be with you, Westerville!",
    "Cinco de Mayo":                     "Celebrating community and culture here in Westerville today!",
    "Juneteenth":                        "Honoring freedom and the spirit of community here in Westerville.",
    "Juneteenth National Independence Day": "Honoring freedom and the spirit of community here in Westerville.",
    "Independence Day":                  "Westerville is lighting up for the Fourth of July!",
    "Labor Day":                         "Honoring the workers who keep Westerville great — enjoy the day!",
    "Halloween":                         "Trick or treat, Westerville — stay safe and have a spooky night!",
    "Veterans Day":                      "Grateful for the veterans who call Westerville home.",
    "Thanksgiving":                      "Counting our blessings and community here in Westerville today!",
    "Christmas Eve":                     "The holiday spirit is alive and well in Westerville!",
    "Christmas Day":                     "Wishing all of Westerville a very Merry Christmas!",
    "New Year's Eve":                    "One more day of great things in Westerville before the new year!",
    "Washington's Birthday":             "A day to reflect on leadership and civic pride in Westerville.",
    "Memorial Day":                      "Remembering and honoring those who served from our community.",
    "Columbus Day":                      "Exploring what's new in Westerville this Columbus Day!",
    "Indigenous Peoples Day":            "Recognizing and honoring indigenous heritage here in central Ohio.",
}


# ── Public API ────────────────────────────────────────────────────────────────

def get_today_holiday(
    date: datetime.date | None = None,
) -> tuple[str, str] | None:
    """
    Return (holiday_name, emoji) if today is a recognized holiday, else None.

    Checks official US holidays via the `holidays` library first (if installed),
    then falls back to the hardcoded unofficial/fun holidays dict.

    Args:
        date: Date to check (defaults to today).

    Returns:
        A (name, emoji) tuple, or None if it's a regular day.
    """
    if date is None:
        date = datetime.date.today()
    year = date.year

    # Official US holidays (requires the `holidays` library)
    if _HAS_HOLIDAYS_LIB:
        us = _holidays_lib.US(years=year)
        if date in us:
            name = us[date]
            return (name, _emoji_for_official(name))

    # Unofficial / fun holidays (always available)
    unofficial = _unofficial_holidays(year)
    if date in unofficial:
        return unofficial[date]

    return None


def get_holiday_greeting(holiday_name: str) -> str:
    """
    Return a short festive opening line for the email, keyed by holiday name.

    Tries an exact dict lookup first, then a substring match, then a generic fallback.

    Args:
        holiday_name: Name returned by get_today_holiday().

    Returns:
        A one-sentence festive opener, e.g. "The luck of the Irish is with Westerville today!"
    """
    if holiday_name in _GREETINGS:
        return _GREETINGS[holiday_name]
    # Partial match (e.g. "Juneteenth National Independence Day" -> "Juneteenth")
    for key, greeting in _GREETINGS.items():
        if key.lower() in holiday_name.lower() or holiday_name.lower() in key.lower():
            return greeting
    return f"Happy {holiday_name}, Westerville!"


# ── Holiday-themed event filtering ────────────────────────────────────────────

_HOLIDAY_KEYWORDS: dict[str, list[str]] = {
    "new year":         ["new year", "countdown", "ball drop", "fireworks", "midnight"],
    "valentine":        ["valentine", "love", "heart", "romance", "sweetheart", "galentine"],
    "super bowl":       ["super bowl", "big game", "watch party", "football"],
    "easter":           ["easter", "egg hunt", "bunny", "spring festival"],
    "st. patrick":      ["patrick", "irish", "shamrock", "green", "clover", "parade", "celtic"],
    "april fools":      ["april fools", "comedy", "joke", "improv"],
    "star wars":        ["star wars", "may the 4th", "jedi", "force"],
    "cinco de mayo":    ["cinco de mayo", "mexican", "fiesta", "margarita", "taco"],
    "juneteenth":       ["juneteenth", "freedom", "african american", "black history"],
    "independence":     ["fourth of july", "4th of july", "fireworks", "independence", "parade", "patriot"],
    "labor day":        ["labor day", "end of summer", "cookout"],
    "halloween":        ["halloween", "haunted", "costume", "trick", "treat", "spooky", "scary", "pumpkin", "fall fest"],
    "veterans":         ["veteran", "military", "honor", "memorial", "armed forces"],
    "thanksgiving":     ["thanksgiving", "turkey", "harvest", "gratitude", "pie"],
    "christmas":        ["christmas", "holiday", "tree", "santa", "caroling", "xmas", "winter festival", "nutcracker"],
}


def filter_holiday_events(events: list[dict], holiday_name: str) -> list[dict]:
    """
    Filter a list of event dicts to those thematically related to the given holiday.

    Args:
        events:       List of event dicts with at least a 'name' key.
        holiday_name: Name returned by get_today_holiday().

    Returns:
        Subset of events whose names contain holiday-related keywords.
        Returns [] if no keyword match is found for the holiday.
    """
    holiday_lc = holiday_name.lower()
    keywords: list[str] = []
    for holiday_key, kws in _HOLIDAY_KEYWORDS.items():
        if holiday_key in holiday_lc or holiday_lc in holiday_key:
            keywords = kws
            break

    if not keywords:
        return []

    return [
        e for e in events
        if any(kw in e.get("name", "").lower() for kw in keywords)
    ]
