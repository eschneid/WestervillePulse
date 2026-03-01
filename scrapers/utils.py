"""
WestervillePulse — Shared Scraper Utilities
============================================
Common helpers imported by all scrapers. To use from any scraper:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from utils import elapsed, find_db_ids_path, load_dotenv_files, load_seen_set, save_seen_set
"""

import json
import time
from pathlib import Path
from dotenv import load_dotenv


def load_dotenv_files(script_file: str) -> None:
    """Load .env from the calling script's directory and its parent (project root)."""
    here = Path(script_file).resolve().parent
    load_dotenv(here / ".env")
    load_dotenv(here.parent / ".env")


def find_db_ids_path(script_file: str) -> Path:
    """Walk up from the calling script's directory to find database_ids.json."""
    check = Path(script_file).resolve().parent
    for _ in range(3):
        candidate = check / "database_ids.json"
        if candidate.exists():
            return candidate
        check = check.parent
    cwd_candidate = Path.cwd() / "database_ids.json"
    if cwd_candidate.exists():
        return cwd_candidate
    return Path("database_ids.json")


def elapsed(start: float) -> str:
    """Format elapsed time since start as a human-readable string."""
    s = time.time() - start
    return f"{s:.1f}s" if s < 60 else f"{int(s // 60)}m {int(s % 60)}s"


def load_seen_set(path: Path) -> set:
    """Load a dedup cache (JSON list on disk) into a Python set."""
    if path.exists():
        with open(path) as f:
            return set(json.load(f))
    return set()


def save_seen_set(path: Path, seen: set) -> None:
    """Persist a dedup set to disk as a sorted JSON list."""
    with open(path, "w") as f:
        json.dump(sorted(seen), f, indent=2)
