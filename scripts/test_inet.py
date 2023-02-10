#!/usr/bin/env python3

## cron
## @reboot sleep 120 && /home/pi/test_inet.py
##

import requests
import http.client as httplib
import time

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



def return_uptime():
    with open('/proc/uptime', 'r') as f:
        seconds = float(f.readline().split()[0])

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
           telegram_bot_sendtext("Internet connection was established after a power outage in {}".format(return_uptime()))
           retry = False
    except:
           time.sleep(60)
