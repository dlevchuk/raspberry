import logging
import os
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
CHERNIHIV_LAT = 51.456421277890946
CHERNIHIV_LON = 31.126549118658463
CHERNIHIV_ICAO = "UKRR"

def get_metar_data(icao_code: str) -> Optional[Dict[str, Any]]:
    """Get METAR data for aviation weather including cloud ceiling."""
    try:
        url = "https://aviationweather.gov/api/data/metar"
        params = {
            "ids": icao_code,
            "format": "json",
            "taf": "false"
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data[0] if data else None
    except requests.RequestException as e:
        logger.error(f"METAR request error: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error getting METAR data: {e}")
        return None

def get_open_meteo_data(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Get detailed weather from Open-Meteo."""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,"
                       "wind_gusts_10m,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,"
                       "visibility,pressure_msl",
            "hourly": "temperature_2m,wind_speed_10m,cloud_cover",
            "timezone": "Europe/Kiev",
            "forecast_days": 1
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Open-Meteo request error: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error getting Open-Meteo data: {e}")
        return None

def format_wind_direction(degrees: Optional[float]) -> str:
    """Convert wind direction to cardinal points."""
    if degrees is None:
        return "N/A"
    
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    idx = int((degrees + 11.25) / 22.5) % 16
    return directions[idx]

def parse_clouds_from_metar(metar_text: str) -> str:
    """Extract cloud layers from raw METAR text with heights."""
    if not metar_text:
        return "No cloud data"
    
    clouds = []
    # Cloud abbreviations mapping
    cloud_types = {
        'FEW': 'Few',
        'SCT': 'Scattered', 
        'BKN': 'Broken',
        'OVC': 'Overcast',
        'CLR': 'Clear',
        'SKC': 'Clear'
    }
    
    parts = metar_text.split()
    for part in parts:
        for cloud_abbr, cloud_name in cloud_types.items():
            if part.startswith(cloud_abbr):
                if cloud_abbr in ['CLR', 'SKC']:
                    return "Clear sky"
                
                # Extract altitude (in hundreds of feet)
                # Example: FEW020 -> 020
                alt_str = part.replace(cloud_abbr, '')[:3]
                if alt_str.isdigit():
                    altitude_ft = int(alt_str) * 100
                    altitude_m = int(altitude_ft * 0.3048)
                    clouds.append(f"{cloud_name}: base {altitude_m}m ({altitude_ft}ft)")
    
    return "\n".join(clouds) if clouds else "No significant clouds"

def format_cloud_layers(weather: Dict[str, Any]) -> str:
    """Format cloud layers with approximate heights."""
    if not weather or 'current' not in weather:
        return "No data"
    
    current = weather['current']
    cloud_low = current.get('cloud_cover_low', 0)
    cloud_mid = current.get('cloud_cover_mid', 0)
    cloud_high = current.get('cloud_cover_high', 0)
    
    layers = []
    
    # Low clouds: 0-2000m
    if cloud_low > 10:
        layers.append(f"Low clouds ({cloud_low}%): 0-2000m")
    
    # Mid clouds: 2000-6000m
    if cloud_mid > 10:
        layers.append(f"Mid clouds ({cloud_mid}%): 2000-6000m")
    
    # High clouds: 6000-13000m
    if cloud_high > 10:
        layers.append(f"High clouds ({cloud_high}%): 6000-13000m")
    
    if not layers:
        total_cover = current.get('cloud_cover', 0)
        if total_cover < 10:
            return "Clear sky"
        else:
            return f"Cloud cover: {total_cover}% (layer heights unavailable)"
    
    return "\n".join(layers)

def create_message(metar: Optional[Dict[str, Any]], weather: Optional[Dict[str, Any]]) -> str:
    """Format weather data into Telegram message."""
    # Timezones
    kyiv_tz = ZoneInfo("Europe/Kiev")
    utc_tz = ZoneInfo("UTC")
    
    now_utc = datetime.now(utc_tz)
    now_local = now_utc.astimezone(kyiv_tz)
    
    timestamp_utc = now_utc.strftime("%Y-%m-%d %H:%M UTC")
    timestamp_local = now_local.strftime("%Y-%m-%d %H:%M %Z")
    
    msg = f"✈️ **Aviation Weather for Chernihiv (UKRR)**\n"
    msg += f"📅 {timestamp_local}\n"
    msg += f"🌍 {timestamp_utc}\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Temperature and humidity
    if weather and 'current' in weather:
        current = weather['current']
        temp = current.get('temperature_2m', 'N/A')
        humidity = current.get('relative_humidity_2m', 'N/A')
        msg += f"🌡 Temperature: {temp}°C\n"
        msg += f"💧 Humidity: {humidity}%\n\n"
    
    # Wind data in m/s
    if weather and 'current' in weather:
        current = weather['current']
        wind_speed_kmh = current.get('wind_speed_10m', 0)
        # Convert km/h to m/s
        wind_speed_ms = round(wind_speed_kmh / 3.6, 1) if isinstance(wind_speed_kmh, (int, float)) else 0
        wind_dir = current.get('wind_direction_10m', None)
        wind_gust_kmh = current.get('wind_gusts_10m', None)
        
        wind_cardinal = format_wind_direction(wind_dir)
        msg += f"💨 Wind: {wind_speed_ms} m/s from {wind_cardinal} ({wind_dir}°)\n"
        
        if wind_gust_kmh:
            wind_gust_ms = round(wind_gust_kmh / 3.6, 1)
            msg += f"💨 Gusts: {wind_gust_ms} m/s\n"
        msg += "\n"
    
    # Cloud data from METAR (base heights)
    if metar:
        msg += f"☁️ **Clouds from METAR:**\n"
        clouds = parse_clouds_from_metar(metar.get('rawOb', ''))
        msg += f"{clouds}\n\n"
    
    # Cloud layers from Open-Meteo
    if weather:
        msg += f"☁️ **Cloud Layers:**\n"
        cloud_layers = format_cloud_layers(weather)
        msg += f"{cloud_layers}\n\n"
    
    # Total cloud cover
    if weather and 'current' in weather:
        cloud_cover = weather['current'].get('cloud_cover', 'N/A')
        msg += f"☁️ Total Cloud Cover: {cloud_cover}%\n\n"
    
    # Visibility and pressure
    if weather and 'current' in weather:
        current = weather['current']
        visibility = current.get('visibility', 'N/A')
        pressure = current.get('pressure_msl', 'N/A')
        if visibility != 'N/A':
             # Visibility in km
            msg += f"👁 Visibility: {visibility/1000:.1f} km\n"
        msg += f"🔽 Pressure: {pressure} hPa\n\n"
    
    # Raw METAR
    if metar:
        msg += f"📋 Raw METAR:\n`{metar.get('rawOb', 'N/A')}`"
    elif not weather:
        msg += "\n⚠️ No weather data available from any source."

    return msg

def send_telegram(message: str) -> bool:
    """Send message to Telegram."""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not bot_token or not chat_id:
        logger.error("Missing Telegram credentials (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    try:
        response = requests.post(
            url,
            json={
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            },
            timeout=10
        )
        response.raise_for_status()
        logger.info("Message sent successfully")
        return True
    except requests.RequestException as e:
        logger.error(f"Telegram request error: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error sending Telegram message: {e}")
        return False

def main():
    logger.info(f"Fetching weather data for {CHERNIHIV_ICAO}...")
    
    # Get data from both sources
    metar = get_metar_data(CHERNIHIV_ICAO)
    weather = get_open_meteo_data(CHERNIHIV_LAT, CHERNIHIV_LON)
    
    if not metar and not weather:
        err_msg = "⚠️ Failed to fetch weather data from ALL sources."
        logger.error(err_msg)
        # Try to notify user about complete failure if possible, 
        # though if internet is down this won't work anyway.
        send_telegram(err_msg)
        return
    
    if not metar:
        logger.warning(f"Failed to fetch METAR data for {CHERNIHIV_ICAO}")
    if not weather:
        logger.warning("Failed to fetch Open-Meteo data")

    # Create and send message
    message = create_message(metar, weather)
    
    # Debug log the message content instead of just print
    # logger.debug(f"Generated message:\n{message}") 
    
    send_telegram(message)

if __name__ == "__main__":
    main()