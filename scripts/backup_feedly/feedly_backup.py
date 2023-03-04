#!/usr/bin/env python3

import io
import json
import requests
import time
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

feedly_token = os.environ.get("FEEDLY_ACCESS_TOKEN")
feedly_user_id = os.environ.get("FEEDLY_USER_ID")

folder = '/home/pi/docker/syncthing/sync/backup/feedly_backup/'
isDirExist = os.path.exists(folder)
if not isDirExist:
  os.mkdir(folder)

filename_opml = folder + 'feedly_export_opml_' + datetime.now().strftime("%Y_%m_%d") + '.opml'
filename_boards = folder + 'feedly_export_boards_' + datetime.now().strftime("%Y_%m_%d") + '.txt'

headers = {'Authorization' : 'OAuth '+ feedly_token}

url_opml = 'https://cloud.feedly.com/v3/opml'
#get boards list
url_boards = 'https://cloud.feedly.com/v3/boards'

def telegram_bot_sendtext(bot_message):
   bot_token = os.environ.get("BOT_TOKEN")
   bot_chatID = os.environ.get("BOT_CHAT_ID")
   send_text = 'https://api.telegram.org/bot' + bot_token + '/sendMessage?chat_id=' + bot_chatID + '&parse_mode=Markdown&text=' + bot_message
   response = requests.get(send_text)

opml = requests.get(url_opml, headers = headers)
boards = requests.get(url_boards, headers = headers)

#save opml
if opml.status_code == 200:
   with open(filename_opml, 'wb') as f:
    try:
      f.write(opml.content)
      telegram_bot_sendtext("Feedly opml backup created successfully")
    except ValueError as error:
      telegram_bot_sendtext(error)

else:
    telegram_bot_sendtext('Error: Saved items couldn’t be fetched')
    telegram_bot_sendtext('Status code: ' + str(opml.status_code))
#    print(opml.json())
    exit(1)

#save boards
if boards.status_code == 200:
   with open(filename_boards, 'w') as f:
    try:
       data = json.dumps(boards.json(), separators=(',',':'))
       dictData = json.loads(data)
       url_list = []
       for id in dictData:
          url = 'https://cloud.feedly.com/v3/streams/contents?streamId=' + id['id'] +'&count=10000'
          url_list.append(url)
       for url in url_list:
         d = requests.get(url, headers = headers)
         data = json.dumps(d.json(), separators=(',',':'))
         dictData = json.loads(data)
         for items in dictData['items']:
           url = items['alternate']
           f.write(str(url) + "\n")
       telegram_bot_sendtext("Feedly boards backup created successfully")
    except ValueError as error:
      telegram_bot_sendtext(error)

else:
    telegram_bot_sendtext('Error: Saved items couldn’t be fetched')
    telegram_bot_sendtext('Status code: ' + str(boards.status_code))
#    print(boards.json())
    exit(1)