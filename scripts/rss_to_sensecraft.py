#!/usr/bin/env python3
"""Fetch RSS sources, pick one randomly (no consecutive repeat),
and push 2 items with source name to SenseCraft HMI."""

import os, re, sys, random, json
import feedparser, requests
from html import unescape

API_KEY = os.environ.get("SENSECRAFT_API_KEY")
DEVICE_ID = os.environ.get("SENSECRAFT_DEVICE_ID")
SOURCES_RAW = os.environ.get("RSS_SOURCES",
    "源1|https://这里填RSS地址1")
SUMMARY_MAX = int(os.environ.get("SUMMARY_MAX", "150"))
PICK_COUNT = int(os.environ.get("PICK_COUNT", "2"))

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


def build_item(title, summary, date_str):
    summary_clean = clean_html(summary)
    if SUMMARY_MAX > 0 and len(summary_clean) > SUMMARY_MAX:
        summary_clean = summary_clean[:SUMMARY_MAX].rstrip("，。；,.;") + "…"
    return {
        "title": title,
        "summary": summary_clean,
        "date": date_str,
    }


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

# Read last used source from cache file (if exists)
last_source = ""
cache_path = "last_source.txt"
if os.path.exists(cache_path):
    with open(cache_path) as f:
        last_source = f.read().strip()
        print(f"Last source was: [{last_source}]")

# Exclude last source to avoid consecutive repeat
candidates = [s for s in all_sources if s[0] != last_source]
if not candidates:
    candidates = all_sources

# Pick one random source
name, url = random.choice(candidates)
print(f"Randomly picked: [{name}]")

# Save current source to cache file
with open(cache_path, "w") as f:
    f.write(name)

print(f"Fetching: {url}")

feed = feedparser.parse(url)
if feed.bozo and not feed.entries:
    print(f"ERROR: Failed to parse feed")
    sys.exit(1)

entries = feed.entries[:]
print(f"Available: {len(entries)} items")

valid = []
for entry in entries:
    title = entry.get("title", "").strip()
    if not title:
        continue
    item = build_item(
        title=title,
        summary=entry.get("summary", "") or entry.get("description", ""),
        date_str=format_date(entry.get("published", "") or entry.get("pubDate", "")),
    )
    valid.append(item)

pick = min(PICK_COUNT, len(valid))
if pick < PICK_COUNT:
    print(f"WARNING: Only {len(valid)} valid items, picking all")

chosen = random.sample(valid, pick)
print(f"Picked {pick} items")

# Push to SenseCraft
data = {}
for i, item in enumerate(chosen, 1):
    data[f"news{i}_title"] = item["title"]
    data[f"news{i}_summary"] = item["summary"]
    data[f"news{i}_date"] = item["date"]
data["source_name"] = name  # 来源名称

print(f"\n=== Pushing {pick} items from [{name}] ===")
for i, item in enumerate(chosen, 1):
    print(f"  news{i}:")
    print(f"    title:   {item['title']}")
    print(f"    summary: {item['summary'][:60]}...")
    print(f"    date:    {item['date']}")
print(f"  source:   {name}")

payload = {"device_id": int(DEVICE_ID), "data": data}
resp = requests.post(
    "https://sensecraft-hmi-api.seeed.cc/api/v1/user/device/push_data",
    headers={"api-key": API_KEY, "Content-Type": "application/json"},
    json=payload, timeout=30,
)

result = resp.json()
if resp.status_code == 200 and result.get("code") == 200:
    print(f"\nSUCCESS: {pick} items from [{name}] pushed!")
    sys.exit(0)
else:
    print(f"\nERROR: {resp.status_code} - {result}")
    sys.exit(1)
