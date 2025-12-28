import warnings
warnings.filterwarnings("ignore")

import os, json, requests
from datetime import datetime, timedelta
import cloudscraper
from bs4 import BeautifulSoup

URLS = [
    {
        "name": "М.Коцюбинського 11",
        "url": "https://chernigiv.energy-ua.info/grafik/МИХАЙЛО-КОЦЮБИНСЬКЕ/М.Коцюбинського/11"
    }
]

BOT_TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]

CACHE_FILE = "sent.json"
WINDOW_MIN = 30
WINDOW_MAX = 0  

def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}
    )

if os.path.exists(CACHE_FILE):
    sent = json.load(open(CACHE_FILE))
else:
    sent = []

now = datetime.now()
scraper = cloudscraper.create_scraper()

for item in URLS:
    r = scraper.get(item["url"], timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    spans = soup.select("div.periods_items > span")

    for s in spans:
        b = s.find_all("b")
        if len(b) < 2:
            continue

        start = datetime.combine(now.date(), datetime.strptime(b[0].text, "%H:%M").time())
        end   = datetime.combine(now.date(), datetime.strptime(b[1].text, "%H:%M").time())

        for t, label, msg in [
            (start, "start", f"⚡ Відключення о ({b[0].text}–{b[1].text})"),
            (end, "end", f"💡 Світло повернеться о ({b[1].text})"),
        ]:
            delta = (t - now).total_seconds() / 60
            key = f"{item['name']}|{label}|{t.isoformat()}"

            if WINDOW_MAX <= delta <= WINDOW_MIN and key not in sent:
                send(f"{item['name']}\n{msg}")
                sent.append(key)

json.dump(sent, open(CACHE_FILE, "w"))