import warnings
warnings.filterwarnings("ignore")

import os, requests, json, sys
from datetime import datetime, timedelta
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
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")  # Get free key at scraperapi.com

WINDOW_MIN = 30
WINDOW_MAX = 0  
DAILY_SENT_FILE = "daily_sent.json"

def send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram error: {e}")

def fetch_with_proxy(url):
    """Fetch URL through ScraperAPI proxy"""
    if SCRAPER_API_KEY:
        print("Using ScraperAPI proxy...")
        proxy_url = "http://api.scraperapi.com"
        params = {
            'api_key': SCRAPER_API_KEY,
            'url': url,
            'render': 'true',
            'country_code': 'ua',  # Use Ukraine proxy
            'premium': 'true',     # Use premium proxy pool
            'wait_for_selector': 'div.periods_items'  # Wait for content
        }
        response = requests.get(proxy_url, params=params, timeout=90)
        print(f"Status: {response.status_code}")
        print(f"Response preview: {response.text[:500]}")
        return response.text
    else:
        print("No proxy key, trying direct...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        return response.text

def should_send_daily():
    ukraine_tz = pytz.timezone('Europe/Kyiv')
    today = datetime.now(ukraine_tz).date().isoformat()
    if os.path.exists(DAILY_SENT_FILE):
        try:
            with open(DAILY_SENT_FILE) as f:
                data = json.load(f)
            return data.get("last_sent") != today
        except:
            return True
    return True

def mark_daily_sent():
    ukraine_tz = pytz.timezone('Europe/Kyiv')
    with open(DAILY_SENT_FILE, "w") as f:
        json.dump({"last_sent": datetime.now(ukraine_tz).date().isoformat()}, f)

ukraine_tz = pytz.timezone('Europe/Kyiv')
now = datetime.now(ukraine_tz)

all_outages = {}

print("Starting scraper...")

for item in URLS:
    print(f"\nFetching: {item['url']}")
    
    try:
        html = fetch_with_proxy(item["url"])
        print(f"HTML length: {len(html)}")
        
        # Check if blocked
        if "Just a moment" in html or len(html) < 1000:
            print("❌ Still blocked or invalid response")
            all_outages[item["name"]] = []
            continue
        
        soup = BeautifulSoup(html, "html.parser")
        spans = soup.select("div.periods_items > span")
        print(f"✓ Found {len(spans)} span elements")
        
        outages = []
        for s in spans:
            b = s.find_all("b")
            if len(b) < 2:
                continue
            
            try:
                start = datetime.combine(now.date(), datetime.strptime(b[0].text.strip(), "%H:%M").time())
                end   = datetime.combine(now.date(), datetime.strptime(b[1].text.strip(), "%H:%M").time())
                start = ukraine_tz.localize(start)
                end = ukraine_tz.localize(end)
                outages.append((b[0].text.strip(), b[1].text.strip(), start, end))
                print(f"  - Outage: {b[0].text.strip()} - {b[1].text.strip()}")
            except Exception as e:
                print(f"  ! Parse error: {e}")
                continue
        
        all_outages[item["name"]] = outages
        print(f"✓ Total outages: {len(outages)}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        all_outages[item["name"]] = []

print(f"\n{'='*50}")
print("Results:")
for k, v in all_outages.items():
    print(f"{k}: {[(s, e) for s, e, _, _ in v]}")
print(f"{'='*50}\n")

# Send daily message
if should_send_daily():
    print("Sending daily message...")
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
    print("✓ Daily message sent")

# Individual notifications
print("\nChecking notifications...")
for item in URLS:
    outages = all_outages.get(item["name"], [])
    for start_time, end_time, start, end in outages:
        for t, label, msg in [
            (start, "start", f"⚡ Відключення о ({start_time}–{end_time})"),
            (end, "end", f"💡 Світло повернеться о ({end_time})"),
        ]:
            delta = (t - now).total_seconds() / 60
            if WINDOW_MAX <= delta <= WINDOW_MIN:
                print(f"Sending: {msg}")
                send(f"{item['name']}\n{msg}")

print("\n✓ Done")