#!/usr/bin/env python3
"""Fetch RSS sources, pick unique sources randomly, push to SenseCraft HMI."""

import os, re, sys, random, json, time
from datetime import datetime, timedelta, timezone
import feedparser, requests
from html import unescape

API_KEY = os.environ.get("SENSECRAFT_API_KEY")
DEVICE_ID = os.environ.get("SENSECRAFT_DEVICE_ID")
SOURCES_RAW = os.environ.get("RSS_SOURCES",
    "源1|https://这里填RSS地址1")
PICK_COUNT = int(os.environ.get("PICK_COUNT", "3"))

if not API_KEY or not DEVICE_ID:
    print("ERROR: SENSECRAFT_API_KEY and SENSECRAFT_DEVICE_ID must be set")
    sys.exit(1)


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'[\n\r\t]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def format_date(pub_date):
    if not pub_date:
        return ""
    m = re.match(r'(\d{4}-\d{2}-\d{2})', pub_date)
    if m:
        return m.group(1)
    m = re.search(r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})', pub_date, re.I)
    months = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
              'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
    if m:
        return f"{m.group(3)}-{months.get(m.group(2),'00')}-{int(m.group(1)):02d}"
    m = re.search(r'(\d{4})', pub_date)
    if m:
        return m.group(1)
    return pub_date[:10]


def is_recent(published_parsed):
    if not published_parsed:
        return True
    try:
        pub_time = datetime(*published_parsed[:6], tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        return pub_time >= cutoff
    except Exception:
        return True


# Parse sources
all_sources = []
for s in SOURCES_RAW.split(","):
    parts = s.strip().split("|")
    if len(parts) == 2:
        all_sources.append((parts[0], parts[1]))
    else:
        print(f"WARNING: Skipping invalid source: {s}")

if not all_sources:
    print("ERROR: No valid RSS sources configured")
    sys.exit(1)

# Read last used source to avoid consecutive repeat
last_source = ""
if os.path.exists("last_source.txt"):
    with open("last_source.txt") as f:
        last_source = f.read().strip()
    print(f"Last source was: [{last_source}]")

# Pick PICK_COUNT different sources
candidates = [s for s in all_sources if s[0] != last_source]
if not candidates:
    candidates = all_sources

sources_to_fetch = []
temp_pool = candidates[:]
for _ in range(PICK_COUNT):
    if not temp_pool:
        break
    choice = random.choice(temp_pool)
    sources_to_fetch.append(choice)
    temp_pool = [s for s in temp_pool if s[0] != choice[0]]

# Save first source to cache (prevent consecutive repeat next run)
if sources_to_fetch:
    with open("last_source.txt", "w") as f:
        f.write(sources_to_fetch[0][0])

print(f"Picked {len(sources_to_fetch)} sources:")
for i, (n, _) in enumerate(sources_to_fetch, 1):
    print(f"  {i}. [{n}]")

# Fetch 1 item from each source
chosen = []
for src_name, src_url in sources_to_fetch:
    print(f"  Fetching: [{src_name}]")
    feed = feedparser.parse(src_url)
    if feed.bozo and not feed.entries:
        print(f"    WARNING: Failed to parse, skip")
        continue
    valid = []
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        if not title or not is_recent(entry.get("published_parsed")):
            continue
        valid.append({
            "title": clean_text(title),
            "date": format_date(entry.get("published", "") or entry.get("pubDate", "")),
        })
    if not valid:
        print(f"    WARNING: No valid items, skip")
        continue
    item = random.choice(valid)
    chosen.append({"source": src_name, **item})
    print(f"    Got 1 item")

if not chosen:
    print("ERROR: No items fetched")
    sys.exit(1)

# Push to SenseCraft
data = {}
for i, item in enumerate(chosen, 1):
    data[f"news{i}_title"] = item["title"]
    data[f"news{i}_source_date"] = f"{item['source']}·{item['date']}"

print(f"\n=== Pushing {len(chosen)} items ===")
for i, item in enumerate(chosen, 1):
    print(f"  news{i}: [{item['source']}] {item['title'][:50]}...")
    print(f"         {item['source']}·{item['date']}")

payload = {"device_id": int(DEVICE_ID), "data": data}
resp = requests.post(
    "https://sensecraft-hmi-api.seeed.cc/api/v1/user/device/push_data",
    headers={"api-key": API_KEY, "Content-Type": "application/json"},
    json=payload, timeout=30,
)

result = resp.json()
if resp.status_code == 200 and result.get("code") == 200:
    print(f"\nSUCCESS: pushed!")
    sys.exit(0)
else:
    print(f"\nERROR: {resp.status_code} - {result}")
    sys.exit(1)
