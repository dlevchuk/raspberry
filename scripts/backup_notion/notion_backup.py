import requests
import os
import datetime
import json
from dotenv import load_dotenv


load_dotenv()

timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
folder = 'notionbackup_' + timestamp

os.mkdir(folder)
notion_token = os.environ.get("NOTION_INTEGRATION_TOKEN")

headers = {
  'Authorization': notion_token,
  'Notion-Version': '2022-06-28',      #notion api version
  'Content-Type': 'application/json',
}

response = requests.post('https://api.notion.com/v1/search', headers=headers)

for block in response.json()['results']:
  with open(f'{folder}/{block["id"]}.json', 'w') as file:
    file.write(json.dumps(block))

  child_blocks = requests.get(
    f'https://api.notion.com/v1/blocks/{block["id"]}/children',
    headers=headers,
  )
  if child_blocks.json()['results']:
    os.mkdir(folder + f'/{block["id"]}')

    for child in child_blocks.json()['results']:
      with open(f'{folder}/{block["id"]}/{child["id"]}.json', 'w') as file:
        file.write(json.dumps(child))
