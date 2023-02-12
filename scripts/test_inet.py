#!/usr/bin/env python3

### cron
### @reboot sleep 120 && /home/pi/test_inet.py
### 2min to boot router and provider switch

import requests
import http.client as httplib
import time
import subprocess
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env.


def have_internet():
    conn = httplib.HTTPSConnection("8.8.8.8", timeout=5)
    try:
        conn.request("HEAD", "/")
        return True
    except Exception:
        return False
    finally:
        conn.close()


def poweroff_start_time():
    output = subprocess.run(["journalctl", "--list-boots"], capture_output=True, text=True).stdout
    latest_boot = output.strip().split("\n")[-2]
    date_string = latest_boot.split(" ")[-3:]
    date = " ".join(date_string)
    return date


def outage_duration(start_time):
    start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S %Z")
    now = datetime.now()
    diff = now - start_time
    seconds = diff.total_seconds()
    minutes = int(seconds // 60)
    hours = int(minutes // 60)
    days = int(hours // 24)
    return str(days) + " days " + str(hours % 24) + " hours " + str(minutes % 60) + " minutes"


def telegram_bot_sendtext(bot_message):
   bot_token = os.environ.get("BOT_TOKEN")
   bot_chatID = os.environ.get("BOT_CHAT_ID")
   send_text = 'https://api.telegram.org/bot' + bot_token + '/sendMessage?chat_id=' + bot_chatID + '&parse_mode=Markdown&text=' + bot_message
   response = requests.get(send_text)


retry = True
while retry:
    try:
        conn = have_internet()
        if(conn == True):
           telegram_bot_sendtext("Internet connection was established after a power outage {} that lasted {}".format(poweroff_start_time(), outage_duration(poweroff_start_time())))
           retry = False
    except:
           time.sleep(60)