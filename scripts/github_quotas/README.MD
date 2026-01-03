# get github quotas

⚠️ **DEPRECATED**: This script and workflow are no longer functional as GitHub has deprecated the billing API endpoints used by this script. The API endpoints (`/users/{username}/settings/billing/*`) are no longer available.

This script was designed to get notifications to telegram about your github account quotas.


## Installation:

 Requirements

     Python 3.x
     requests
     load_dotenv
     json


## How to run:

1. Obtain a Github developer token.

2. Create .env file and add your tokens as environment variables:
   ```
     GITHUB_TOKEN=
     GITHUB_USER=
     #telegram
     BOT_TOKEN=
     BOT_CHAT_ID=
   ```
