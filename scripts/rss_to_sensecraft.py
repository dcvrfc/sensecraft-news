#!/usr/bin/env python3
"""Fetch multiple RSS sources and push random items to SenseCraft HMI."""

import os, re, sys, random
import feedparser, requests
from html import unescape

API_KEY = os.environ.get("SENSECRAFT_API_KEY")
DEVICE_ID = os.environ.get("SENSECRAFT_DEVICE_ID")
SOURCES_RAW = os.environ.get("RSS_SOURCES",
    "源1|https://这里填RSS地址1|2")

if not API_KEY or not DEVICE_ID:
    print("ERROR: SENSECRAFT_API_KEY and SENSECRAFT_DEVICE_ID must be set")
    sys.exit(1)


def clean_html(html_text):
    text = re.sub(r'<[^>]+>', ' ', html_text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def format_date(pub_date):
    if not pub_date:
        return ""
    m = re.match(r'(\d{4}-\d{2}-\d{2})', pub_date)
    return m.group(1) if m else pub_date[:10]


def build_item_text(title, summary, date_str):
    summary_clean = clean_html(summary)
    parts = [title]
    if summary_clean:
        parts.append(summary_clean)
    if date_str:
        parts.append(date_str)
    return "\n".join(parts)


# Parse sources
sources = []
for s in SOURCES_RAW.split(","):
    parts = s.strip().split("|")
    if len(parts) == 3:
        sources.append((parts[0], parts[1], int(parts[2])))
    else:
        print(f"WARNING: Skipping invalid source: {s}")

if not sources:
    print("ERROR: No valid RSS sources configured")
    sys.exit(1)

# Fetch all sources and randomly pick items
all_items = []
for name, url, count in sources:
    print(f"\n[{name}] Fetching: {url}")
    feed = feedparser.parse(url)
    if feed.bozo and not feed.entries:
        print(f"  WARNING: Failed to parse, skipping")
        continue

    entries = feed.entries[:]
    print(f"  Available: {len(entries)} items")

    # Build list of valid items
    valid = []
    for entry in entries:
        title = entry.get("title", "").strip()
        if not title:
            continue
        text = build_item_text(
            title=title,
            summary=entry.get("summary", "") or entry.get("description", ""),
            date_str=format_date(entry.get("published", "") or entry.get("pubDate", "")),
        )
        valid.append(text)

    # Randomly pick `count` items (without duplicates)
    pick = min(count, len(valid))
    if pick < count:
        print(f"  WARNING: Only {len(valid)} valid items, picking all")

    chosen = random.sample(valid, pick)
    for item in chosen:
        all_items.append({"source": name, "text": item})

    print(f"  Picked {pick} items randomly")

if not all_items:
    print("\nERROR: No news fetched")
    sys.exit(1)

# Shuffle all items so sources are mixed
random.shuffle(all_items)

# Push to SenseCraft
data = {}
for i, item in enumerate(all_items, 1):
    data[f"news{i}"] = item["text"]

print(f"\n=== Pushing {len(all_items)} items (random order) ===")
for i, item in enumerate(all_items, 1):
    print(f"  news{i}: [{item['source']}]")
    for line in item["text"].split("\n"):
        print(f"    {line}")

payload = {"device_id": int(DEVICE_ID), "data": data}
resp = requests.post(
    "https://sensecraft-hmi-api.seeed.cc/api/v1/user/device/push_data",
    headers={"api-key": API_KEY, "Content-Type": "application/json"},
    json=payload, timeout=30,
)

result = resp.json()
if resp.status_code == 200 and result.get("code") == 200:
    print(f"\nSUCCESS: {len(data)} items pushed!")
    sys.exit(0)
else:
    print(f"\nERROR: {resp.status_code} - {result}")
    sys.exit(1)
