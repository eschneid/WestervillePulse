"""
WestervillePulse — Run All Scrapers
====================================
Runs all 5 scrapers in sequence. One failing won't stop the others.
Results are logged to runs.log with a timestamp.

Usage:
    python run_all.py
"""

import os
import re
import sys
import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

SCRAPERS = [
    ("📰  News",          "scrapers/news_scraper.py"),
    ("🍽️  Restaurants",   "scrapers/restaurants_scraper.py"),
    ("🏢  SOS Filings",   "scrapers/sos_scraper.py"),
    ("🎉  Events",         "scrapers/events_scraper.py"),
    ("🏗️  Development",    "scrapers/development_scraper.py"),
    ("📧  Email Digest",   "scrapers/digest.py"),
]

LOG_PATH = HERE / "runs.log"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _elapsed(start: float) -> str:
    s = time.time() - start
    return f"{s:.1f}s" if s < 60 else f"{int(s // 60)}m {int(s % 60)}s"


def _parse_added(output: str) -> int:
    """Extract the number of records added from scraper stdout.

    All scrapers print a line like 'Added N articles/businesses/events/projects'.
    Returns 0 if not found (e.g. 'Nothing new today').
    """
    m = re.search(r"Added (\d+)", output)
    return int(m.group(1)) if m else 0


# ── Run one scraper ───────────────────────────────────────────────────────────

def run_scraper(label: str, script: str) -> dict:
    """Run a single scraper in a subprocess and return a result dict."""
    start = time.time()
    script_path = HERE / script

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(HERE),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    output  = proc.stdout
    if proc.stderr:
        output += proc.stderr

    success = proc.returncode == 0

    return {
        "label":      label,
        "success":    success,
        "returncode": proc.returncode,
        "elapsed":    _elapsed(start),
        "added":      _parse_added(output) if success else None,
        "output":     output,
    }


# ── Log writer ────────────────────────────────────────────────────────────────

def write_log(run_start: datetime, results: list) -> None:
    """Append a structured run summary to runs.log."""
    timestamp   = run_start.strftime("%Y-%m-%d %H:%M:%S UTC")
    total_added = sum(r["added"] or 0 for r in results)
    n_ok  = sum(1 for r in results if r["success"])
    n_err = len(results) - n_ok

    lines = [
        "",
        "=" * 65,
        f"RUN: {timestamp}",
        f"{'OK' if n_err == 0 else 'PARTIAL'} — {n_ok}/{len(results)} scrapers succeeded  |  {total_added} total records added",
        "-" * 65,
    ]

    for r in results:
        status    = "OK " if r["success"] else "ERR"
        added_str = f"+{r['added']}" if r["added"] is not None else "FAILED"
        lines.append(f"  [{status}]  {r['label']:<22}  {added_str:>8} records  {r['elapsed']:>8}")

    for r in results:
        if not r["success"]:
            lines.append(f"\n  --- {r['label']} (exit {r['returncode']}) ---")
            tail = r["output"].strip().splitlines()[-20:]
            lines.extend(f"  | {line}" for line in tail)

    lines.append("")

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    run_start   = datetime.now(timezone.utc)
    total_start = time.time()

    print()
    print("🌆  WestervillePulse — Run All Scrapers")
    print("=" * 65)
    print(f"   Started : {run_start.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print()

    results = []

    for label, script in SCRAPERS:
        print("─" * 65)
        print(f"  Running {label} ...")
        print()

        result = run_scraper(label, script)
        results.append(result)

        # Echo scraper output indented so it's readable inline
        for line in result["output"].splitlines():
            print(f"  {line}")

        verdict = "✅ Done" if result["success"] else f"❌ FAILED (exit {result['returncode']})"
        print(f"\n  → {verdict}  ({result['elapsed']})")
        print()

    # ── Summary ───────────────────────────────────────────────────────────────
    total_added = sum(r["added"] or 0 for r in results)
    n_err       = sum(1 for r in results if not r["success"])

    print("=" * 65)
    print("📊  Summary")
    print("─" * 65)

    for r in results:
        icon      = "✅" if r["success"] else "❌"
        added_str = f"+{r['added']}" if r["added"] is not None else "FAILED"
        print(f"  {icon}  {r['label']:<22}  {added_str:>8} records  {r['elapsed']:>8}")

    print("─" * 65)
    print(f"      {'TOTAL':<22}  {total_added:>8} records  {_elapsed(total_start):>8}")
    print()

    if n_err:
        print(f"  ⚠️   {n_err} scraper(s) failed — check output above or runs.log.")
    else:
        print("  ✅  All scrapers completed successfully.")

    print(f"  📄  Log appended to: {LOG_PATH}")
    print()

    write_log(run_start, results)
    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
