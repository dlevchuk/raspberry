# light outage
This script monitors power outage schedules from chernigiv.energy-ua.info and sends Telegram notifications about scheduled outages and when power is restored.

## Installation:

 Requirements

     Python 3.x
     cloudscraper
     beautifulsoup4
     requests
     pytz


## How to run:

1. Create .env file and add your tokens as environment variables:
   ```
     #telegram
     TG_TOKEN=
     TG_CHAT_ID=
   ```

2. Run the script:
   ```
     python power.py
   ```

## Features:

- Daily schedule: Sends a daily summary of all scheduled outages for the day
- Real-time notifications: Sends alerts 30 minutes before outages start and when power is restored
- Timezone-aware: Uses Ukraine timezone (Europe/Kyiv) for accurate scheduling
