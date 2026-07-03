# Meteo Data

Automated weather fetching script for Slavutych that combines aviation weather (METAR from UKRR) and detailed forecast data. The script sends formatted weather updates via Telegram.

## Overview

The `meteo.py` script fetches weather data from two sources:
1. **Aviation Weather Center** (METAR data) for precise aviation cloud base readings.
2. **Open-Meteo API** for detailed current weather conditions (temperature, humidity, wind).

It formats this data into a comprehensive report and sends it to a specified Telegram chat.

## Features

- **Mixed Data Sources**: Combines METAR aviation data with general weather API data.
- **Detailed Cloud Reporting**:
  - Decodes RAW METAR strings to provide precise cloud base heights (e.g., "Broken: base 1005m").
  - Categorizes cloud layers from Open-Meteo (Low/Mid/High).
- **Comprehensive Metrics**:
  - Temperature & Humidity
  - Wind speed (m/s), direction (cardinal + degrees), and gusts
  - Visibility settings
  - Atmospheric pressure
- **Telegram Integration**: Formatted Markdown messages with headers and icons.

## Usage

### Manual Execution

```bash
python3 meteo.py
```

### Configuration

The script requires the following environment variables for Telegram integration:

- `TELEGRAM_BOT_TOKEN`: Your Telegram Bot API token.
- `TELEGRAM_CHAT_ID`: The target chat ID where messages will be sent.

Constants for location (Slavutych) are hardcoded in the script:
- ICAO Code: `UKRR` (nearest reporting airfield)
- Coordinates: `51.5206 N, 30.7569 E`

## Dependencies

- Python 3.9+ (requires `zoneinfo`)
- `requests`

Install dependencies:
```bash
pip install requests
```

## Output Format

The script sends a Telegram message resembling:

```text
✈️ **Aviation Weather for Slavutych (METAR: UKRR)**
📅 2024-01-01 12:00 EET
🌍 2024-01-01 10:00 UTC
━━━━━━━━━━━━━━━━━━━━

🌡 Temperature: 20.5°C
💧 Humidity: 45%

💨 Wind: 5.2 m/s from NW (315°)
💨 Gusts: 8.5 m/s

☁️ **Clouds from METAR:**
Scattered: base 1200m (3937ft)

☁️ **Cloud Layers:**
Low clouds (15%): 0-2000m

🔽 Pressure: 1013 hPa
```
