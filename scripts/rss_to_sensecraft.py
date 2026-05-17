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


def clean_text(text):
    """Remove any newlines/tabs from text, keep it as one line."""
    if not text:
        return ""
    return re.sub(r'[\n\r\t]+', ' ', text).strip()


def format_date(pub_date):
    if not pub_date:
        return ""
    # Try YYYY-MM-DD (e.g. 2026-05-17 14:08:32 +0800)
    m = re.match(r'(\d{4}-\d{2}-\d{2})', pub_date)
    if m:
        return m.group(1)
    # Try "DD Mon YYYY" (e.g. Sun, 17 May 2026)
    m = re.search(r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})', pub_date, re.I)
    months = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
              'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
    if m:
        return f"{m.group(3)}-{months.get(m.group(2),'00')}-{int(m.group(1)):02d}"
    # Fallback: just the year
    m = re.search(r'(\d{4})', pub_date)
    if m:
        return m.group(1)
    return pub_date[:10]


def build_item(title, summary, date_str):
    summary_clean = clean_html(summary)
    if SUMMARY_MAX > 0 and len(summary_clean) > SUMMARY_MAX:
        summary_clean = summary_clean[:SUMMARY_MAX].rstrip("，。；,.;") + "…"
    return {
        "title": clean_text(title),
        "summary": clean_text(summary_clean),
        "date": clean_text(date_str),
    }


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

# Read last used source from cache
last_source = ""
if os.path.exists("last_source.txt"):
    with open("last_source.txt") as f:
        last_source = f.read().strip()
    print(f"Last source was: [{last_source}]")

candidates = [s for s in all_sources if s[0] != last_source]
if not candidates:
    candidates = all_sources

# 选第一个源
name1, url1 = random.choice(candidates)
print(f"1st source: [{name1}]")

# 保存第一个源到缓存（避免下次连续重复）
with open("last_source.txt", "w") as f:
    f.write(name1)

# 选第二个源（跟第一个不同）
remaining = [s for s in all_sources if s[0] != name1]
name2, url2 = random.choice(remaining) if remaining else (name1, url1)
print(f"2nd source: [{name2}]")

# 取两个源各 1 条
chosen = []
for src_name, src_url in [(name1, url1), (name2, url2)]:
    print(f"  Fetching: [{src_name}]")
    feed = feedparser.parse(src_url)
    if feed.bozo and not feed.entries:
        print(f"    WARNING: Failed to parse, skip")
        continue
    valid = []
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        if not title:
            continue
        valid.append(build_item(
            title=title,
            summary=entry.get("summary", "") or entry.get("description", ""),
            date_str=format_date(entry.get("published", "") or entry.get("pubDate", "")),
        ))
    if not valid:
        print(f"    WARNING: No valid items, skip")
        continue
    item = random.choice(valid)
    chosen.append({"source": src_name, **item})
    print(f"    Got 1 item")

if not chosen:
    print("ERROR: No items fetched")
    sys.exit(1)

data = {}
for i, item in enumerate(chosen, 1):
    data[f"news{i}_title"] = item["title"]
    data[f"news{i}_summary"] = item["summary"]
    data[f"news{i}_date"] = item["date"]
    data[f"news{i}_source"] = item["source"]

print(f"\n=== Pushing {len(chosen)} items ===")
for i, item in enumerate(chosen, 1):
    print(f"  news{i}: [{item['source']}] {item['title'][:50]}...")

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
