import warnings
warnings.filterwarnings("ignore")

import os, requests, json, sys
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
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
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram error: {e}")

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

print("Starting scraper with Playwright + Stealth...")

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-web-security'
        ]
    )
    
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
        locale='uk-UA',
        timezone_id='Europe/Kiev'
    )
    
    page = context.new_page()
    stealth_sync(page)
    
    for item in URLS:
        print(f"\nFetching: {item['url']}")
        
        try:
            response = page.goto(item["url"], timeout=60000, wait_until="domcontentloaded")
            print(f"Response status: {response.status}")
            
            # Wait for potential Cloudflare challenge
            print("Waiting for page to settle...")
            page.wait_for_timeout(10000)
            
            html = page.content()
            print(f"HTML length: {len(html)}")
            
            # Check if blocked
            if "Just a moment" in html or "challenge-platform" in html:
                print("❌ Still blocked by Cloudflare")
                all_outages[item["name"]] = []
                continue
            
            # Check if we have the content
            if "periods_items" not in html:
                print("⚠️ Content not found, saving HTML for debug...")
                with open("debug.html", "w", encoding="utf-8") as f:
                    f.write(html)
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
            print(f"✓ Total outages for {item['name']}: {len(outages)}")
            
        except Exception as e:
            print(f"❌ Error for {item['name']}: {e}")
            import traceback
            traceback.print_exc()
            all_outages[item["name"]] = []
    
    browser.close()

print(f"\n{'='*50}")
print("All outages collected:")
print(json.dumps({k: [(s, e) for s, e, _, _ in v] for k, v in all_outages.items()}, indent=2, ensure_ascii=False))
print(f"{'='*50}\n")

# Send daily guarantee message if needed
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
else:
    print("Daily message already sent today")

# Process individual notifications
print("\nChecking for upcoming notifications...")
for item in URLS:
    outages = all_outages.get(item["name"], [])
    
    for start_time, end_time, start, end in outages:
        for t, label, msg in [
            (start, "start", f"⚡ Відключення о ({start_time}–{end_time})"),
            (end, "end", f"💡 Світло повернеться о ({end_time})"),
        ]:
            delta = (t - now).total_seconds() / 60
            
            if WINDOW_MAX <= delta <= WINDOW_MIN:
                print(f"Sending notification: {msg} (in {delta:.1f} min)")
                send(f"{item['name']}\n{msg}")

print("\n✓ Script completed")