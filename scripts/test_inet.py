#!/usr/bin/env python3

### cron
### @reboot sleep 120 && /home/pi/test_inet.py
###

import requests
import http.client as httplib
import time
import subprocess
import datetime

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




def time_since_last_boot():
    result = subprocess.run(["journalctl", "--list-boots"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = result.stdout.decode()
    lines = output.split("\n")
    for line in lines:
        if " - " in line:
            boot_time_str = line.split(" - ")[1]
            boot_time = datetime.datetime.strptime(boot_time_str, "%a %b %d %H:%M:%S %Y")
            now = datetime.datetime.now()
            time_since_boot = now - boot_time
            return time_since_boot




#def return_uptime():
#    with open('/proc/uptime', 'r') as f:
#        seconds = float(f.readline().split()[0])
#
#    minutes = int(seconds // 60)
#    hours = int(minutes // 60)
#    days = int(hours // 24)
#
#    return str(days) + " days " + str(hours % 24) + " hours " + str(minutes % 60) + " minutes"




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
           telegram_bot_sendtext("Internet connection was established after a power outage in {}".format(time_since_last_boot()))
           retry = False
    except:
           time.sleep(60)
