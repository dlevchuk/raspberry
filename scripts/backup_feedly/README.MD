# feedly backup
This script allows you to backup your Feedly data, including your OPML file and saved articles, and receive notifications via Telegram about the backup status.
> [!IMPORTANT]
> Starting October 2023, Feedly developer tokens will require an upgrade to Feedly Pro. The backup process was rebuilt through [Axiom](https://axiom.ai/).

## Installation:

 Requirements

     Python 3.x
     requests
     load_dotenv


## How to run:

1. ~~Obtain a Feedly developer token. You can get one [here](https://feedly.com/v3/auth/dev) Please note that tokens in the free subscription expire in 30 days, and refresh tokens are only available in paid subscriptions.~~

2. Create .env file and add your tokens as environment variables:
   ```
     FEEDLY_ACCESS_TOKEN=
     FEEDLY_USER_ID=
     #telegram
     BOT_TOKEN=
     BOT_CHAT_ID=
   ```
