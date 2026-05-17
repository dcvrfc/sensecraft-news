#!/usr/bin/env python3
"""Fetch multiple RSS sources and push to SenseCraft HMI."""

import os, re, sys
import feedparser, requests
from html import unescape

API_KEY = os.environ.get("SENSECRAFT_API_KEY")
DEVICE_ID = os.environ.get("SENSECRAFT_DEVICE_ID")
SOURCES_RAW = os.environ.get("RSS_SOURCES",
    "源1|https://这里填RSS地址1|3")
SUMMARY_LEN = int(os.environ.get("SUMMARY_LEN", "60"))

if not API_KEY or not DEVICE_ID:
    print("ERROR: SENSECRAFT_API_KEY and SENSECRAFT_DEVICE_ID must be set")
    sys.exit(1)


def clean_html(html_text):
    """Strip HTML tags, unescape entities, return plain text."""
    text = re.sub(r'<[^>]+>', ' ', html_text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def format_date(pub_date):
    """Format pubDate to YYYY-MM-DD."""
    if not pub_date:
        return ""
    # Try to extract date from various formats
    m = re.match(r'(\d{4}-\d{2}-\d{2})', pub_date)
    if m:
        return m.group(1)
    return pub_date[:10] if len(pub_date) >= 10 else pub_date


def build_item_text(title, summary, date_str):
    """Build multi-line text for one news item."""
    summary_clean = clean_html(summary)[:SUMMARY_LEN]
    if summary_clean:
        summary_clean = summary_clean.rstrip("，。；,.;") + "…"
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

# Fetch all sources
all_items = []
for name, url, count in sources:
    print(f"\n[{name}] Fetching: {url}")
    feed = feedparser.parse(url)
    if feed.bozo and not feed.entries:
        print(f"  WARNING: Failed to parse, skipping")
        continue
    fetched = 0
    for entry in feed.entries[:count]:
        title = entry.get("title", "").strip()
        if not title:
            continue
        text = build_item_text(
            title=title,
            summary=entry.get("summary", "") or entry.get("description", ""),
            date_str=format_date(entry.get("published", "") or entry.get("pubDate", "")),
        )
        all_items.append({"source": name, "text": text})
        fetched += 1
    print(f"  Got {fetched} items")

if not all_items:
    print("\nERROR: No news fetched")
    sys.exit(1)

# Push to SenseCraft
data = {}
for i, item in enumerate(all_items, 1):
    data[f"news{i}"] = item["text"]

print(f"\n=== Pushing {len(all_items)} items ===")
for i, item in enumerate(all_items, 1):
    print(f"  news{i}: [{item['source']}]")
    for line in item["text"].split("\n"):
        print(f"    {line}")
    print()

payload = {"device_id": int(DEVICE_ID), "data": data}
resp = requests.post(
    "https://sensecraft-hmi-api.seeed.cc/api/v1/user/device/push_data",
    headers={"api-key": API_KEY, "Content-Type": "application/json"},
    json=payload, timeout=30,
)

result = resp.json()
if resp.status_code == 200 and result.get("code") == 200:
    print(f"SUCCESS: {len(data)} items pushed!")
    sys.exit(0)
else:
    print(f"ERROR: {resp.status_code} - {result}")
    sys.exit(1)
