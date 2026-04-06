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
GITHUB_TOKEN = os.environ["GH_TOKEN"]
GITHUB_USERNAME = os.environ["GH_USERNAME"]
README_PATH = os.path.join(os.path.dirname(__file__), "..", "README.md")
LINES_PER_KM = 50

# ---------------------------------------------------------------------------
# Trail library — Québec, Eastern Canada, Adirondacks
# Each entry: (min_km, max_km, name, region, description, elevation_m)
# ---------------------------------------------------------------------------
TRAILS = [
    # Short — local Québec
    (0,   5,   "Parc du Mont-Royal loop",               "Montréal, QC",          "a lap around the mountain — practically a coffee run",                                      233),
    (5,   10,  "Sentier du Belvédère, Mont Saint-Bruno", "Montérégie, QC",        "through maple forest above the St. Lawrence plain",                                         218),
    (10,  18,  "Sentier des Contreforts segment",        "Laurentians, QC",       "rolling hardwood hills north of the city",                                                  420),
    (18,  28,  "Mont Orford summit loop",                "Estrie, QC",            "a proper summit scramble in the Eastern Townships",                                         853),
    (28,  40,  "Sentier de la Rivière-du-Nord",          "Laurentians, QC",       "following the river north through cedar and birch",                                         350),
    (40,  55,  "Mont Tremblant backcountry loop",        "Laurentians, QC",       "through old-growth forest to Québec's highest Laurentian peak",                             968),
    (55,  75,  "Tour du Mont-Mégantic",                  "Estrie, QC",            "circling a dark-sky reserve and an astronomical observatory",                              1105),
    (75,  100, "Sentier des Caps de Charlevoix",         "Charlevoix, QC",        "cliff-edge trails above the St. Lawrence with views that go on forever",                    600),
    (100, 125, "Corridor Aérobique — full traverse",     "Laurentians, QC",       "Québec's classic multi-use trail threading the pines end to end",                          500),
    (125, 155, "Parc de la Gaspésie — Mont Albert loop", "Gaspésie, QC",          "an arctic plateau above the treeline, caribou country",                                   1151),
    (155, 200, "Sentier international des Appalaches (QC segment)", "Gaspésie, QC","the Québec leg of the International Appalachian Trail along dramatic ridgelines",         1268),
    # Adirondacks
    (0,   7,   "Cascade Mountain",                      "Adirondacks, NY",       "the most-climbed High Peak — a short push to an open rocky summit",                       1295),
    (7,   16,  "Giant Mountain loop",                   "Adirondacks, NY",       "above treeline with long views over Lake Champlain and into Québec",                      1412),
    (16,  27,  "Marcy Dam to Avalanche Lake",            "Adirondacks, NY",       "through a glacial gorge to one of the Adirondacks' most dramatic spots",                   880),
    (27,  42,  "Mount Marcy via Van Hoevenberg",         "Adirondacks, NY",       "the highest point in New York — above the clouds on a clear day",                         1629),
    (42,  62,  "Algonquin and Wright Peak loop",         "Adirondacks, NY",       "two High Peaks in one push — alpine meadows and exposed ridgeline",                       1559),
    (62,  95,  "Great Range Traverse",                   "Adirondacks, NY",       "the crown jewel of Adirondack hiking — seven peaks in a single day",                      1559),
    (95,  135, "Northville–Placid Trail (south half)",   "Adirondacks, NY",       "through the remote Adirondack interior — wilderness ponds and boreal silence",             800),
    (135, 185, "Northville–Placid Trail (full)",         "Adirondacks, NY",       "170 km of true backcountry from the southern foothills to Lake Placid",                    900),
    # Longer regional routes
    (185, 270, "Long Trail — Vermont (full)",            "Vermont, USA",          "the oldest long-distance trail in the US, end to end through the Green Mountains",        1340),
    (270, 390, "Sentier national du Québec (central)",   "QC",                    "the spine of Québec's backcountry, deep into the Canadian Shield",                         900),
    (390, 560, "International Appalachian Trail (full)", "QC / NB / NL",          "from the end of the Appalachians in Québec to the Strait of Belle Isle",                  1268),
    (560, 9999,"Trans Canada Trail (QC section)",        "QC",                    "the longest trail network on Earth — a good chunk of it through Québec forest",            800),
]

# Flavour copy — no emojis
GRIND_LINES = [
    "Instead, the IDE stayed open.",
    "The terminal won.",
    "Hiking boots: dry. Keyboard: worn.",
    "Nature will have to wait.",
    "No blisters. Just git blame.",
    "The mountains can wait one more week.",
    "Commit streak holding. Trail streak paused.",
    "Elevation gained: 0 m. PRs merged: several.",
    "The only peak climbed was the call stack.",
    "The forest is still there. It's patient.",
    "Somewhere a trail sign is collecting dew.",
    "The trees aren't going anywhere.",
]

ON_TRAIL_LINES = [
    "He's on the trails right now.",
    "No commits. Probably somewhere in the Laurentians.",
    "The boots are on. The laptop is not.",
    "Gone hiking. Back Monday.",
    "Out there earning the elevation.",
    "Touch grass: status confirmed.",
    "The forest won this week.",
    "No lines written. Many steps taken.",
]

# ---------------------------------------------------------------------------
# SVG forest banner — muted dark greens, pine silhouettes, no emojis
# ---------------------------------------------------------------------------
SVG_BANNER = '''<p align="center">
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 110" width="800" height="110">
  <rect width="800" height="110" fill="#0d1810"/>
  <!-- back ridge -->
  <polygon points="0,85 70,42 140,85"   fill="#182d1e"/>
  <polygon points="90,85 180,28 270,85" fill="#1c3423"/>
  <polygon points="210,85 310,18 410,85" fill="#182d1e"/>
  <polygon points="360,85 455,32 550,85" fill="#1c3423"/>
  <polygon points="500,85 595,20 690,85" fill="#182d1e"/>
  <polygon points="640,85 720,38 800,85" fill="#1c3423"/>
  <!-- mid layer -->
  <polygon points="20,85  65,52  110,85"  fill="#22452a"/>
  <polygon points="100,85 155,40 210,85"  fill="#274e30"/>
  <polygon points="195,85 255,46 315,85"  fill="#22452a"/>
  <polygon points="305,85 370,36 435,85"  fill="#274e30"/>
  <polygon points="425,85 485,44 545,85"  fill="#22452a"/>
  <polygon points="535,85 598,38 661,85"  fill="#274e30"/>
  <polygon points="645,85 705,50 765,85"  fill="#22452a"/>
  <polygon points="740,85 785,42 800,85"  fill="#274e30"/>
  <!-- front trees -->
  <polygon points="0,85   32,62   64,85"  fill="#193820"/>
  <polygon points="55,85  92,56  129,85"  fill="#1e4226"/>
  <polygon points="125,85 168,58 211,85"  fill="#193820"/>
  <polygon points="215,85 262,50 309,85"  fill="#1e4226"/>
  <polygon points="315,85 358,60 401,85"  fill="#193820"/>
  <polygon points="405,85 450,53 495,85"  fill="#1e4226"/>
  <polygon points="500,85 545,56 590,85"  fill="#193820"/>
  <polygon points="595,85 640,48 685,85"  fill="#1e4226"/>
  <polygon points="685,85 730,60 775,85"  fill="#193820"/>
  <polygon points="760,85 790,64 800,85"  fill="#1e4226"/>
  <!-- ground -->
  <rect x="0" y="85" width="800" height="25" fill="#111e14"/>
  <!-- faint crescent -->
  <circle cx="700" cy="20" r="11" fill="#0d1810"/>
  <circle cx="706" cy="20" r="11" fill="#b8cca0" opacity="0.12"/>
  <!-- wordmark -->
  <text x="400" y="72" text-anchor="middle"
        font-family="monospace" font-size="10" fill="#4d7a52"
        letter-spacing="5" opacity="0.9">trails not taken</text>
</svg>
</p>'''

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
    data = gh_get(
        f"https://api.github.com/users/{GITHUB_USERNAME}/repos"
        "?type=owner&sort=pushed&per_page=100"
    )
    return [r["full_name"] for r in data if isinstance(r, dict)]


def lines_this_week(repos: list[str]) -> tuple[int, int, int]:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total_add, total_del, commit_count = 0, 0, 0

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
    """Returns (full_day_name, lines) only for days where lines > 0."""
    results = []
    for i in range(6, -1, -1):
        day = datetime.now(timezone.utc) - timedelta(days=i)
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
        if day_lines > 0:
            results.append((day.strftime("%A"), day_lines))

    return results


# ---------------------------------------------------------------------------
# Trail matching
# ---------------------------------------------------------------------------

def pick_trail(km: float) -> dict:
    for min_km, max_km, name, region, desc, elev in TRAILS:
        if min_km <= km < max_km:
            return {"name": name, "region": region, "desc": desc, "elev": elev}
    _, _, name, region, desc, elev = TRAILS[-1]
    return {"name": name, "region": region, "desc": desc, "elev": elev}


def pick_line(lines_list: list[str], seed_extra: str = "") -> str:
    import hashlib
    week_str = datetime.now(timezone.utc).strftime("%Y-%W") + seed_extra
    idx = int(hashlib.md5(week_str.encode()).hexdigest(), 16) % len(lines_list)
    return lines_list[idx]


# ---------------------------------------------------------------------------
# README rendering
# ---------------------------------------------------------------------------

def build_day_table(breakdown: list[tuple[str, int]]) -> str:
    if not breakdown:
        return ""
    max_lines = max(lines for _, lines in breakdown)
    rows = []
    for day, lines in breakdown:
        km = lines / LINES_PER_KM
        bar_len = max(1, int((lines / max_lines) * 18))
        bar = "█" * bar_len + "░" * (18 - bar_len)
        rows.append(f"| {day:<9s} | `{bar}` | {lines:,} lines | {km:.1f} km |")
    header = "| Day | | Lines | km |\n|-----|---|-------|-----|"
    return header + "\n" + "\n".join(rows)


def render_block(
    total_lines: int,
    km: float,
    trail: dict,
    breakdown: list[tuple[str, int]],
) -> str:
    updated = datetime.now(timezone.utc).strftime("%B %d, %Y")

    if total_lines == 0:
        on_trail_msg = pick_line(ON_TRAIL_LINES)
        return f"""<!-- HIKE:START -->
{SVG_BANNER}

### trails not taken

> *{on_trail_msg}*

<sub>checked {updated} · 1 km = {LINES_PER_KM} lines · [how this works](scripts/update_hike.py)</sub>
<!-- HIKE:END -->"""

    grind_line = pick_line(GRIND_LINES, seed_extra=str(total_lines))
    day_table = build_day_table(breakdown)
    table_section = f"\n{day_table}\n" if day_table else ""

    return f"""<!-- HIKE:START -->
{SVG_BANNER}

### trails not taken

> *{total_lines:,} lines this week. That's **{km:.1f} km** — {trail['desc']}.*
> *{grind_line}*

| | |
|---|---|
| trail | {trail['name']} |
| region | {trail['region']} |
| distance equivalent | {km:.1f} km |
| trail elevation | {trail['elev']:,} m |
{table_section}
<sub>updated {updated} · 1 km = {LINES_PER_KM} lines · [how this works](scripts/update_hike.py)</sub>
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

    print(f"Total: {total_lines:,} lines = {km:.1f} km -> {trail['name']}")

    block = render_block(total_lines, km, trail, breakdown)
    update_readme(block)


if __name__ == "__main__":
    main()