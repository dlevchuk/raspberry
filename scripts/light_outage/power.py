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

BOT_TOKEN = os.environ.get("TG_TOKEN")
CHAT_ID = os.environ.get("TG_CHAT_ID")
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")

def send(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Missing Telegram credentials")
        return
    
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
        response.raise_for_status()
        print(f"✓ Message sent")
    except Exception as e:
        print(f"Telegram error: {e}")

def fetch_with_proxy(url):
    if not SCRAPER_API_KEY:
        return requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30).text

    proxy_url = "http://api.scraperapi.com"
    
    # Tier 1: Cheap Attempt (1 credit)
    print("🛰 Attempting Standard Request (1 credit)...")
    cheap_params = {
        'api_key': SCRAPER_API_KEY,
        'url': url,
        'render': 'false',
        'premium': 'false',
        'country_code': 'ua'
    }
    
    try:
        res = requests.get(proxy_url, params=cheap_params, timeout=45)
        # Check if we got actual content or a block page
        if res.status_code == 200 and "periods_items" in res.text:
            print("✅ Success with Standard Request")
            return res.text
    except Exception as e:
        print(f"⚠️ Standard attempt failed: {e}")

    # Tier 2: Premium Escalation (Only if Tier 1 fails)
    print("🚀 Standard failed or blocked. Escalating to Premium...")
    premium_params = cheap_params.copy()
    premium_params.update({
        'premium': 'true',
        'render': 'true', # Only add this if you suspect JS-based blocking
    })
    
    try:
        res = requests.get(proxy_url, params=premium_params, timeout=90)
        return res.text
    except Exception as e:
        print(f"❌ Premium attempt failed: {e}")
        return ""


"""
def fetch_with_proxy(url):
    if SCRAPER_API_KEY:
        print("Using ScraperAPI proxy...")
        proxy_url = "http://api.scraperapi.com"
        params = {
            'api_key': SCRAPER_API_KEY,
            'url': url,
            'render': 'true',
            'country_code': 'ua',
            'premium': 'true',
            'wait_for_selector': 'div.periods_items'
        }
        response = requests.get(proxy_url, params=params, timeout=90)
        print(f"Status: {response.status_code}, Length: {len(response.text)}")
        return response.text
    else:
        print("No proxy, trying direct...")
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=30)
        return response.text
"""


def format_time_delta(minutes):
    if minutes < 60:
        return f"{int(minutes)} хв"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f} год"
    days = hours / 24
    return f"{days:.1f} днів"

ukraine_tz = pytz.timezone('Europe/Kyiv')
now = datetime.now(ukraine_tz)

print(f"Script run at: {now.strftime('%Y-%m-%d %H:%M %Z')}\n")

all_outages = {}

for item in URLS:
    print(f"Fetching: {item['name']}")
    
    try:
        html = fetch_with_proxy(item["url"])
        
        if "Just a moment" in html or len(html) < 1000:
            print("❌ Blocked or invalid response")
            all_outages[item["name"]] = []
            continue
        
        soup = BeautifulSoup(html, "html.parser")
        spans = soup.select("div.periods_items > span")
        print(f"✓ Found {len(spans)} outage periods")
        
        outages = []
        for s in spans:
            b = s.find_all("b")
            if len(b) < 2:
                continue
            
            try:
                start_time = b[0].text.strip()
                end_time = b[1].text.strip()
                
                # Parse times
                start_naive = datetime.combine(now.date(), datetime.strptime(start_time, "%H:%M").time())
                end_naive = datetime.combine(now.date(), datetime.strptime(end_time, "%H:%M").time())
                
                # Make timezone aware BEFORE any comparisons
                start = ukraine_tz.localize(start_naive)
                end = ukraine_tz.localize(end_naive)
                
                # Handle overnight outages
                if end <= start:
                    end += timedelta(days=1)
                
                # If outage already passed today, move to tomorrow
                if start < now:
                    start += timedelta(days=1)
                    end += timedelta(days=1)
                
                outages.append({
                    'start_time': start_time,
                    'end_time': end_time,
                    'start': start,
                    'end': end
                })
                print(f"  - {start_time} – {end_time} ({start.strftime('%d.%m %H:%M')})")
                
            except Exception as e:
                print(f"  ! Parse error: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        all_outages[item["name"]] = outages
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        all_outages[item["name"]] = []

print(f"\n{'='*60}")

# Build message
message_parts = []
message_parts.append(f"📅 <b>Графік відключень</b>")
message_parts.append(f"🕐 {now.strftime('%d.%m.%Y %H:%M')}\n")

for location, outages in all_outages.items():
    message_parts.append(f"🏠 <b>{location}</b>")
    
    if not outages:
        message_parts.append("  ✅ Відключень немає\n")
        continue
    
    # Find next outage
    next_outage = None
    for outage in sorted(outages, key=lambda x: x['start']):
        if outage['start'] > now:
            next_outage = outage
            break
    
    if next_outage:
        delta_min = (next_outage['start'] - now).total_seconds() / 60
        time_str = format_time_delta(delta_min)
        
        message_parts.append(f"  ⚡ Наступне відключення:")
        message_parts.append(f"     Через <b>{time_str}</b>")
        message_parts.append(f"     {next_outage['start_time']} – {next_outage['end_time']}\n")
    
    # Show all outages
    message_parts.append("  📋 Всі відключення:")
    for outage in outages:
        status = ""
        if outage['start'] <= now <= outage['end']:
            status = " 🔴 зараз"
        elif outage['start'] < now:
            status = " ✓ пройшло"
        
        message_parts.append(f"     {outage['start_time']} – {outage['end_time']}{status}")
    
    message_parts.append("")

message = "\n".join(message_parts)

print(message)
print(f"{'='*60}\n")

send(message)

print("✓ Script completed")