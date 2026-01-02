import requests
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# Chernihiv coordinates
LAT = 51.456421277890946
LON = 31.126549118658463
ICAO = "UKRR"  # Chernihiv airport

def get_metar_data(icao_code):
    """Get METAR data for aviation weather including cloud ceiling"""
    try:
        url = f"https://aviationweather.gov/api/data/metar?ids={icao_code}&format=json&taf=false"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data[0] if data else None
    except Exception as e:
        print(f"METAR error: {e}")
        return None

def get_open_meteo_data(lat, lon):
    """Get detailed weather from Open-Meteo"""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&"
            f"current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,"
            f"wind_gusts_10m,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,"
            f"visibility,pressure_msl&"
            f"hourly=temperature_2m,wind_speed_10m,cloud_cover&"
            f"timezone=Europe/Kiev&forecast_days=1"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Open-Meteo error: {e}")
        return None

def format_wind_direction(degrees):
    """Convert wind direction to cardinal points"""
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    idx = int((degrees + 11.25) / 22.5) % 16
    return directions[idx]

def parse_clouds_from_metar(metar_text):
    """Extract cloud layers from raw METAR text with heights"""
    clouds = []
    if not metar_text:
        return "No cloud data"
    
    # Cloud abbreviations: FEW, SCT, BKN, OVC
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
        for cloud_type in cloud_types.keys():
            if part.startswith(cloud_type):
                if cloud_type in ['CLR', 'SKC']:
                    return "Clear sky"
                # Extract altitude (in hundreds of feet)
                alt_str = part.replace(cloud_type, '')[:3]
                if alt_str.isdigit():
                    altitude_ft = int(alt_str) * 100
                    altitude_m = int(altitude_ft * 0.3048)
                    clouds.append(f"{cloud_types[cloud_type]}: base {altitude_m}m ({altitude_ft}ft)")
    
    return "\n".join(clouds) if clouds else "No significant clouds"

def format_cloud_layers(weather):
    """Format cloud layers with approximate heights"""
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

def create_message(metar, weather):
    """Format weather data into Telegram message"""
    # Chernihiv timezone
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
        wind_speed_kmh = current.get('wind_speed_10m', 0)
        wind_speed_ms = round(wind_speed_kmh / 3.6, 1)  # Convert km/h to m/s
        wind_dir = current.get('wind_direction_10m', None)
        wind_gust_kmh = current.get('wind_gusts_10m', None)
        
        wind_cardinal = format_wind_direction(wind_dir) if wind_dir else 'N/A'
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
    
    # Cloud layers with height ranges
    if weather:
        msg += f"☁️ **Cloud Layers:**\n"
        cloud_layers = format_cloud_layers(weather)
        msg += f"{cloud_layers}\n\n"
    
    # Total cloud cover
    if weather and 'current' in weather:
        cloud_cover = current.get('cloud_cover', 'N/A')
        msg += f"☁️ Total Cloud Cover: {cloud_cover}%\n\n"
    
    # Visibility and pressure
    if weather and 'current' in weather:
        visibility = current.get('visibility', 'N/A')
        pressure = current.get('pressure_msl', 'N/A')
        if visibility != 'N/A':
            msg += f"👁 Visibility: {visibility/1000:.1f} km\n"
        msg += f"🔽 Pressure: {pressure} hPa\n\n"
    
    # Raw METAR
    if metar:
        msg += f"📋 Raw METAR:\n`{metar.get('rawOb', 'N/A')}`"
    
    return msg

def send_telegram(message):
    """Send message to Telegram"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not bot_token or not chat_id:
        print("ERROR: Missing Telegram credentials")
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
        print("Message sent successfully")
        return True
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def main():
    print("Fetching weather data for Chernihiv...")
    
    # Get data from both sources
    metar = get_metar_data(ICAO)
    weather = get_open_meteo_data(LAT, LON)
    
    if not metar and not weather:
        send_telegram("⚠️ Failed to fetch weather data for Chernihiv")
        return
    
    # Create and send message
    message = create_message(metar, weather)
    send_telegram(message)

if __name__ == "__main__":
    main()