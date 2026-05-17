#!/usr/bin/env python3
import json, os, sys
import feedparser, requests

API_KEY = os.environ.get("SENSECRAFT_API_KEY")
DEVICE_ID = os.environ.get("SENSECRAFT_DEVICE_ID")
RSS_URL = os.environ.get("RSS_URL", "https://aihot.virxact.com/feed.xml")
MAX_ITEMS = int(os.environ.get("MAX_ITEMS", "5"))

if not API_KEY or not DEVICE_ID:
    print("ERROR: SENSECRAFT_API_KEY and SENSECRAFT_DEVICE_ID must be set")
    sys.exit(1)

feed = feedparser.parse(RSS_URL)
if feed.bozo and not feed.entries:
    print(f"ERROR: Failed to parse RSS: {feed.bozo_exception}")
    sys.exit(1)

data = {}
for i, entry in enumerate(feed.entries[:MAX_ITEMS], 1):
    data[f"news{i}"] = entry.get("title", "")
    print(f"  {i}. {data[f'news{i}']}")

payload = {"device_id": int(DEVICE_ID), "data": data}
resp = requests.post(
    "https://sensecraft-hmi-api.seeed.cc/api/v1/user/device/push_data",
    headers={"api-key": API_KEY, "Content-Type": "application/json"},
    json=payload, timeout=30,
)

result = resp.json()
if resp.status_code == 200 and result.get("code") == 200:
    print(f"\nSUCCESS: {len(data)} news items pushed to SenseCraft!")
    sys.exit(0)
else:
    print(f"\nERROR: {resp.status_code} - {result}")
    sys.exit(1)
