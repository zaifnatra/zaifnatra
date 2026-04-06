#!/usr/bin/env python3
"""
update_hike.py
Fetches the past 7 days of commit activity, converts lines of code to km,
picks a matching trail, and rewrites the HIKE block in README.md.
"""

import os
import re
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GITHUB_TOKEN = os.environ["GH_TOKEN"]          # set as Actions secret
GITHUB_USERNAME = os.environ["GH_USERNAME"]    # e.g. "zaif123"
README_PATH = os.path.join(os.path.dirname(__file__), "..", "README.md")
LINES_PER_KM = 50                              # tune this however you like

# ---------------------------------------------------------------------------
# Trail library
# Each entry: (min_km, max_km, name, region, description, elevation_m, tag)
# ---------------------------------------------------------------------------
TRAILS = [
    (0,   5,   "Parc du Mont-Royal loop",        "Montréal, QC",       "a lazy lap around the mountain — practically a coffee run",                          80,   "urban stroll"),
    (5,   12,  "Sentier de la Rivière-à-Simon",   "Laurentians, QC",    "a quiet riverside trail north of the city",                                          120,  "easy day hike"),
    (12,  22,  "Corridor Aérobique segment",       "Laurentians, QC",    "a slice of Québec's classic multi-use trail through the pines",                      200,  "day hike"),
    (22,  35,  "Mont Orford summit loop",          "Estrie, QC",         "a proper summit scramble in the Eastern Townships",                                   853,  "half-day summit"),
    (35,  55,  "Mont Tremblant backcountry",       "Laurentians, QC",    "through old-growth forest to Québec's highest Laurentian peak",                      968,  "full-day alpine"),
    (55,  80,  "Tour du Mont-Mégantic",            "Estrie, QC",         "circling a dark-sky reserve and an actual astronomical observatory",                  1105, "overnight route"),
    (80,  120, "Sentier des Caps de Charlevoix",   "Charlevoix, QC",     "cliff-edge trails above the St. Lawrence — some of Québec's best views",             600,  "2-day route"),
    (120, 170, "Tour du Mont Blanc (partial)",     "Alps, FR/IT/CH",     "through three countries along the flank of Western Europe's highest peak",           2500, "multi-day alpine"),
    (170, 230, "GR 20 — Corsica (north half)",    "Corsica, FR",        "the hardest long-distance trail in Europe — granite ridges and wild descent",        2706, "expert alpine"),
    (230, 320, "Haute Route Chamonix–Zermatt",    "Alps, FR/CH",        "the classic glacier traverse from Mont Blanc to the Matterhorn",                     3100, "glacier haute route"),
    (320, 450, "Tour des Écrins",                 "Hautes-Alpes, FR",   "a full loop around the wildest massif in the French Alps",                           3200, "remote alpine circuit"),
    (450, 600, "GR 10 — Pyrenees traverse",       "Pyrenees, FR",       "the full length of the French Pyrenees, Atlantic to Mediterranean",                  3298, "thru-hike"),
    (600, 900, "Te Araroa (North Island)",         "New Zealand",        "from Cape Reinga to Wellington — through geothermal plains and volcanic peaks",       1967, "thru-hike"),
    (900, 9999,"Pacific Crest Trail (NorCal)",     "California, USA",    "the legendary spine of the Sierra Nevada — meadows, granite, sky",                   4317, "legendary thru-hike"),
]

# Flavour copy for the "instead he shipped it" line
GRIND_LINES = [
    "Instead, the IDE stayed open.",
    "The terminal won.",
    "Hiking boots: dry. Keyboard: suffering.",
    "Nature will have to wait.",
    "No blisters, just git blame.",
    "The mountains can wait one more week.",
    "Commit streak > trail streak.",
    "Elevation gained: 0 m. PRs merged: several.",
    "The only peak climbed was the call stack.",
]

# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def gh_get(url: str) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "hike-readme-bot/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} for {url}: {e.read().decode()}", file=sys.stderr)
        return []


def get_repos() -> list[str]:
    """Return full_names of repos owned by the user (up to 100)."""
    data = gh_get(
        f"https://api.github.com/users/{GITHUB_USERNAME}/repos"
        "?type=owner&sort=pushed&per_page=100"
    )
    return [r["full_name"] for r in data if isinstance(r, dict)]


def lines_this_week(repos: list[str]) -> tuple[int, int, int]:
    """
    Returns (total_lines, additions, deletions) across all repos
    for commits in the past 7 days authored by GITHUB_USERNAME.
    Uses the /commits endpoint with since/until and sums stats.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    total_add, total_del = 0, 0
    commit_count = 0

    for repo in repos:
        commits = gh_get(
            f"https://api.github.com/repos/{repo}/commits"
            f"?author={GITHUB_USERNAME}&since={since}&until={until}&per_page=100"
        )
        if not isinstance(commits, list):
            continue
        for c in commits:
            sha = c.get("sha", "")
            if not sha:
                continue
            detail = gh_get(f"https://api.github.com/repos/{repo}/commits/{sha}")
            if not isinstance(detail, dict):
                continue
            stats = detail.get("stats", {})
            total_add += stats.get("additions", 0)
            total_del += stats.get("deletions", 0)
            commit_count += 1

    total_lines = total_add + total_del
    print(f"Scanned {commit_count} commits across {len(repos)} repos — {total_lines} lines total")
    return total_lines, total_add, total_del


def daily_breakdown(repos: list[str]) -> list[tuple[str, int]]:
    """Returns (day_label, lines) for each day of the past 7 days."""
    days = []
    for i in range(6, -1, -1):
        day = datetime.now(timezone.utc) - timedelta(days=i)
        days.append(day)

    results = []
    for day in days:
        since = day.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        until = day.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%dT%H:%M:%SZ")
        day_lines = 0
        for repo in repos:
            commits = gh_get(
                f"https://api.github.com/repos/{repo}/commits"
                f"?author={GITHUB_USERNAME}&since={since}&until={until}&per_page=100"
            )
            if not isinstance(commits, list):
                continue
            for c in commits:
                sha = c.get("sha", "")
                if not sha:
                    continue
                detail = gh_get(f"https://api.github.com/repos/{repo}/commits/{sha}")
                if not isinstance(detail, dict):
                    continue
                stats = detail.get("stats", {})
                day_lines += stats.get("additions", 0) + stats.get("deletions", 0)
        results.append((day.strftime("%a"), day_lines))

    return results


# ---------------------------------------------------------------------------
# Trail matching
# ---------------------------------------------------------------------------

def pick_trail(km: float) -> dict:
    for min_km, max_km, name, region, desc, elev, tag in TRAILS:
        if min_km <= km < max_km:
            return {"name": name, "region": region, "desc": desc, "elev": elev, "tag": tag}
    # fallback: last entry
    _, _, name, region, desc, elev, tag = TRAILS[-1]
    return {"name": name, "region": region, "desc": desc, "elev": elev, "tag": tag}


def pick_grind_line(lines: int) -> str:
    import hashlib
    week_str = datetime.now(timezone.utc).strftime("%Y-%W")
    idx = int(hashlib.md5((week_str + str(lines)).encode()).hexdigest(), 16) % len(GRIND_LINES)
    return GRIND_LINES[idx]


# ---------------------------------------------------------------------------
# README rendering
# ---------------------------------------------------------------------------

def build_day_grid(breakdown: list[tuple[str, int]]) -> str:
    rows = []
    for day, lines in breakdown:
        km = lines / LINES_PER_KM
        bar_len = min(20, int(km / 3))  # scale: 3 km per block, max 20
        bar = "█" * bar_len + "░" * (20 - bar_len)
        rows.append(f"| {day:3s} | `{bar}` | {lines:,} lines | {km:.1f} km |")
    header = "| Day | Activity | Lines | km |\n|-----|----------|-------|-----|"
    return header + "\n" + "\n".join(rows)


def render_block(
    total_lines: int,
    km: float,
    trail: dict,
    grind_line: str,
    breakdown: list[tuple[str, int]],
) -> str:
    updated = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    goal_km = 80.0
    pct = min(100, int(km / goal_km * 100))
    progress_bar_len = 20
    filled = int(pct / 100 * progress_bar_len)
    progress = "█" * filled + "░" * (progress_bar_len - filled)

    day_grid = build_day_grid(breakdown)

    return f"""<!-- HIKE:START -->
## 🥾 trails not taken this week

> *{total_lines:,} lines committed. That's **{km:.1f} km** — {trail['desc']}.*
> *{grind_line}*

| | |
|---|---|
| **Trail** | {trail['name']} |
| **Region** | {trail['region']} |
| **Equivalent distance** | {km:.1f} km |
| **Trail elevation** | {trail['elev']:,} m |
| **Difficulty tag** | {trail['tag']} |

**Weekly coding distance** `{progress}` {pct}% of {goal_km:.0f} km goal

{day_grid}

<sub>Updated {updated} · 1 km = {LINES_PER_KM} lines · [how this works](scripts/update_hike.py)</sub>
<!-- HIKE:END -->"""


# ---------------------------------------------------------------------------
# README updater
# ---------------------------------------------------------------------------

def update_readme(block: str) -> None:
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r"<!-- HIKE:START -->.*?<!-- HIKE:END -->"
    if re.search(pattern, content, re.DOTALL):
        new_content = re.sub(pattern, block, content, flags=re.DOTALL)
    else:
        # Append if markers not found
        new_content = content.rstrip() + "\n\n" + block + "\n"

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print("README.md updated successfully.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Fetching repos for @{GITHUB_USERNAME}...")
    repos = get_repos()
    print(f"Found {len(repos)} repos.")

    print("Counting lines from the past 7 days...")
    total_lines, additions, deletions = lines_this_week(repos)

    print("Building daily breakdown...")
    breakdown = daily_breakdown(repos)

    km = total_lines / LINES_PER_KM
    trail = pick_trail(km)
    grind_line = pick_grind_line(total_lines)

    print(f"Total: {total_lines:,} lines = {km:.1f} km → {trail['name']}")

    block = render_block(total_lines, km, trail, grind_line, breakdown)
    update_readme(block)


if __name__ == "__main__":
    main()
