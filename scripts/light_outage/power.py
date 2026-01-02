import warnings
warnings.filterwarnings("ignore")

import os, requests, json, sys
from datetime import datetime, timedelta
import cloudscraper
from bs4 import BeautifulSoup
import pytz

URLS = [
    {
        "name": "М.Коцюбинського 11",
        "url": "https://chernigiv.energy-ua.info/grafik/МИХАЙЛО-КОЦЮБИНСЬКЕ/М.Коцюбинського/11"
    }
]

BOT_TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]

WINDOW_MIN = 30
WINDOW_MAX = 0  
DAILY_SENT_FILE = "daily_sent.json"

def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}
    )

def should_send_daily():
    """Check if we should send the daily guarantee message"""
    ukraine_tz = pytz.timezone('Europe/Kyiv')
    today = datetime.now(ukraine_tz).date().isoformat()
    if os.path.exists(DAILY_SENT_FILE):
        try:
            data = json.load(open(DAILY_SENT_FILE))
            return data.get("last_sent") != today
        except:
            return True
    return True

def mark_daily_sent():
    """Mark that we've sent the daily message today"""
    ukraine_tz = pytz.timezone('Europe/Kyiv')
    json.dump({"last_sent": datetime.now(ukraine_tz).date().isoformat()}, open(DAILY_SENT_FILE, "w"))

# Use Ukraine timezone (Europe/Kyiv)
ukraine_tz = pytz.timezone('Europe/Kyiv')
now = datetime.now(ukraine_tz)
scraper = cloudscraper.create_scraper()

# Collect all outage periods for daily message
all_outages = {}

for item in URLS:
    r = scraper.get(item["url"], timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    spans = soup.select("div.periods_items > span")
    
    outages = []
    for s in spans:
        b = s.find_all("b")
        if len(b) < 2:
            continue

        start = datetime.combine(now.date(), datetime.strptime(b[0].text, "%H:%M").time())
        end   = datetime.combine(now.date(), datetime.strptime(b[1].text, "%H:%M").time())
        # Make datetime timezone-aware
        start = ukraine_tz.localize(start)
        end = ukraine_tz.localize(end)
        outages.append((b[0].text, b[1].text, start, end))
    
    all_outages[item["name"]] = outages

# Send daily guarantee message if needed
if should_send_daily():
    daily_msg = "📋 Графік відключень на сьогодні:\n\n"
    for location, outages in all_outages.items():
        daily_msg += f"🏠 {location}:\n"
        if outages:
            for start_time, end_time, start, end in outages:
                daily_msg += f"  ⚡ {start_time}–{end_time}\n"
        else:
            daily_msg += "  ✅ Відключень немає\n"
        daily_msg += "\n"
    
    send(daily_msg)
    mark_daily_sent()

# Process individual notifications
for item in URLS:
    outages = all_outages.get(item["name"], [])
    
    for start_time, end_time, start, end in outages:
        for t, label, msg in [
            (start, "start", f"⚡ Відключення о ({start_time}–{end_time})"),
            (end, "end", f"💡 Світло повернеться о ({end_time})"),
        ]:
            delta = (t - now).total_seconds() / 60

            if WINDOW_MAX <= delta <= WINDOW_MIN:
                send(f"{item['name']}\n{msg}")
