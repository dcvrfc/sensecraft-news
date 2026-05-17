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
SUMMARY_MAX = int(os.environ.get("SUMMARY_MAX", "80"))
PICK_COUNT = int(os.environ.get("PICK_COUNT", "3"))

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


def clean_summary_junk(text):
    """Remove common junk from summary text (image credits, source notices, etc)."""
    if not text:
        return ""
    # Remove image credit patterns: "NAME/AFP via Getty Images", "AFP via Getty Images", etc.
    text = re.sub(r'\b[A-Za-z\s/]+via Getty Images\b', '', text)
    text = re.sub(r'\b[A-Za-z\s/]+/Getty Images\b', '', text)
    text = re.sub(r'\b[A-Za-z\s/]+/AFP\b', '', text)
    text = re.sub(r'\bAFP via Getty Images\b', '', text)
    text = re.sub(r'\b[A-Za-z\s/]+/Reuters\b', '', text)
    text = re.sub(r'\b[A-Za-z\s/]+/The New York Times\b', '', text)
    text = re.sub(r'\b[A-Za-z\s/]+/Associated Press\b', '', text)
    text = re.sub(r'\b[A-Za-z\s/]+/Agence France-Presse\b', '', text)
    # Remove "IT之家 X月X日消息" prefix
    text = re.sub(r'IT之家\s*\d+\s*月\s*\d+\s*日\s*消息\s*', '', text)
    # Remove "本文来自..." patterns
    text = re.sub(r'本文来自[\u4e00-\u9fff\w]+', '', text)
    # Remove "获取更多RSS" patterns
    text = re.sub(r'获取更多RSS.*', '', text)
    # Remove standalone URLs
    text = re.sub(r'https?://\S+', '', text)
    # Cleanup leading/trailing punctuation from removals
    text = re.sub(r'^[\s/，。；,.;、\\-]+', '', text)
    text = re.sub(r'[\s/，。；,.;、\\-]+$', '', text)
    # Clean up leftover whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def build_item(title, summary, date_str):
    summary_clean = clean_summary_junk(clean_html(summary))
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

# 选 PICK_COUNT 个不同源，各取 1 条
candidates = [s for s in all_sources if s[0] != last_source]
if not candidates:
    candidates = all_sources

sources_to_fetch = []
temp_pool = candidates[:]
for i in range(PICK_COUNT):
    if not temp_pool:
        break
    choice = random.choice(temp_pool)
    sources_to_fetch.append(choice)
    temp_pool = [s for s in temp_pool if s[0] != choice[0]]

# 保存第一个源到缓存（避免下次连续重复）
with open("last_source.txt", "w") as f:
    f.write(sources_to_fetch[0][0])

print(f"Picked {len(sources_to_fetch)} sources:")
for i, (n, _) in enumerate(sources_to_fetch, 1):
    print(f"  {i}. [{n}]")

# 取每个源各 1 条
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
        if not title:
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

# 只推标题和 来源·日期
data = {}
for i, item in enumerate(chosen, 1):
    data[f"news{i}_title"] = item["title"]
    data[f"news{i}_source_date"] = f"{item['source']} · {item['date']}"

print(f"\n=== Pushing {len(chosen)} items ===")
for i, item in enumerate(chosen, 1):
    print(f"  news{i}: [{item['source']}] {item['title'][:50]}...")
    print(f"         {item['source']} · {item['date']}")

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
