import warnings
warnings.filterwarnings("ignore")

import os, requests, json, sys
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
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
    ukraine_tz = pytz.timezone('Europe/Kyiv')
    with open(DAILY_SENT_FILE, "w") as f:
        json.dump({"last_sent": datetime.now(ukraine_tz).date().isoformat()}, f)

ukraine_tz = pytz.timezone('Europe/Kyiv')
now = datetime.now(ukraine_tz)

all_outages = {}

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox'
        ]
    )
    
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
        locale='uk-UA'
    )
    
    page = context.new_page()
    
    for item in URLS:
        print(f"Fetching: {item['url']}")
        try:
            page.goto(item["url"], wait_until="domcontentloaded", timeout=60000)
            
            # Wait for Cloudflare challenge to complete
            page.wait_for_timeout(5000)
            
            # Check if we got through
            page.wait_for_selector("div.periods_items > span", timeout=10000)
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            spans = soup.select("div.periods_items > span")
            
            print(f"Found {len(spans)} spans")
            
            outages = []
            for s in spans:
                b = s.find_all("b")
                if len(b) < 2:
                    continue

                start = datetime.combine(now.date(), datetime.strptime(b[0].text, "%H:%M").time())
                end   = datetime.combine(now.date(), datetime.strptime(b[1].text, "%H:%M").time())
                start = ukraine_tz.localize(start)
                end = ukraine_tz.localize(end)
                outages.append((b[0].text, b[1].text, start, end))
            
            all_outages[item["name"]] = outages
            
        except Exception as e:
            print(f"Error for {item['name']}: {e}")
            all_outages[item["name"]] = []
    
    browser.close()



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