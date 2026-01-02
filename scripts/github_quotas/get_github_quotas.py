import requests
import json
import os
from urllib.parse import quote


github_token = os.environ.get("GITHUB_TOKEN")
github_user = os.environ.get("GITHUB_USER")
#emoji
heavy_check_mark = u'\u2705'
large_red_circle = u'\U0001F534'

message_list = []

def telegram_bot_sendtext(bot_message):
   bot_token = os.environ.get("BOT_TOKEN")
   bot_chatID = os.environ.get("BOT_CHAT_ID")
   
   if not bot_token or not bot_chatID:
       print("Error: BOT_TOKEN or BOT_CHAT_ID not set")
       return
   
   message = "\n".join(bot_message)
   # URL encode the message to handle special characters
   encoded_message = quote(message)
   send_text = f'https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={bot_chatID}&parse_mode=html&text={encoded_message}'
   response = requests.get(send_text)
   
   if response.status_code != 200:
       print(f"Error sending Telegram message: {response.status_code} - {response.text}")


# Validate required environment variables
if not github_token:
    print("Error: GITHUB_TOKEN environment variable is not set")
    exit(1)

if not github_user:
    print("Error: GITHUB_USER environment variable is not set")
    exit(1)

# set the headers for authorization and content type
headers = {
    "Authorization": f"token {github_token}",
    "Accept": "application/vnd.github.v3+json"
}

# make API request to get GitHub shared-storage quotas
url_gh_sh_storage = f'https://api.github.com/users/{github_user}/settings/billing/shared-storage'
response_gh_sh_storage = requests.get(url_gh_sh_storage, headers=headers)

# parse the response and print out the GitHub Packages quotas
if response_gh_sh_storage.status_code == 200:
    data = json.loads(response_gh_sh_storage.content.decode('utf-8'))

    message_list.append("<b>GitHub shared-storage quotas</b>")
    message_list.append(f"  Days left in billing cycle: <u>{data['days_left_in_billing_cycle']}</u>")
    message_list.append(f"  Estimated Packages paid storage for month: <u>{data['estimated_paid_storage_for_month']}</u>")
    message_list.append(f"  Estimated Packages storage for month: <u>{data['estimated_storage_for_month']}</u>")
else:
    message_list.append(f"Error getting GitHub Packages quotas: {response_gh_sh_storage.status_code} - {response_gh_sh_storage.reason} {large_red_circle}")

# make API request to get GitHub action quotas
url_gh_action = f"https://api.github.com/users/{github_user}/settings/billing/actions"
response_gh_action = requests.get(url_gh_action, headers=headers)

if response_gh_action.status_code == 200:
    data = response_gh_action.json()
    if data['total_minutes_used'] > 1500:
        message_list.append(f"\n<b>GitHub action quotas</b> {large_red_circle}")
    else:
        message_list.append(f"\n<b>GitHub action quotas</b> {heavy_check_mark}")

    message_list.append(f"  Total minutes used: <u>{data['total_minutes_used']}</u>")
    message_list.append(f"  Total paid minutes used: <u>{data['total_paid_minutes_used']}</u>")
    message_list.append(f"  Included minutes: <u>{data['included_minutes']}</u>")
    message_list.append("  <i>Minutes used breakdown:</i>")
    breakdown = data["minutes_used_breakdown"]

    for key, value in breakdown.items():
        if value != 0:
            minutes_used_by_os = ": ".join(str(x) for x in (key, value))
            message_list.append(f"   <u>{minutes_used_by_os}</u>")

else:
     message_list.append(f"Error getting GitHub Action quotas: {response_gh_action.status_code} - {response_gh_action.reason} {large_red_circle}")

#Get GitHub Packages billing for a user
url_gh_packages = f"https://api.github.com/users/{github_user}/settings/billing/packages"
response_gh_packages = requests.get(url_gh_packages, headers=headers)

# parse the response and print out the GitHub Packages quotas
if response_gh_packages.status_code == 200:
    data = json.loads(response_gh_packages.content.decode('utf-8'))
    if data['total_gigabytes_bandwidth_used'] > 0.8:
        message_list.append(f"\n<b>GitHub packages quotas</b> {large_red_circle}")
    else:
        message_list.append(f"\n<b>GitHub packages quotas</b> {heavy_check_mark}")

    message_list.append(f"  Total gigabytes bandwidth used: <u>{data['total_gigabytes_bandwidth_used']}</u>")
    message_list.append(f"  Total paid gigabytes bandwidth used: <u>{data['total_paid_gigabytes_bandwidth_used']}</u>")
    message_list.append(f"  Included gigabytes bandwidth: <u>{data['included_gigabytes_bandwidth']}</u>")
else:
    message_list.append(f"Error getting GitHub Packages quotas: {response_gh_packages.status_code} - {response_gh_packages.reason} {large_red_circle}")


telegram_bot_sendtext(message_list)
