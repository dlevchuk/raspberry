import requests
import os
from datetime import datetime

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
            f"wind_gusts_10m,cloud_cover,visibility,pressure_msl&"
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
    """Extract cloud layers from raw METAR text"""
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
                    clouds.append(f"{cloud_types[cloud_type]} at {altitude_ft}ft ({altitude_m}m)")
    
    return "\n".join(clouds) if clouds else "No significant clouds"

def create_message(metar, weather):
    """Format weather data into Telegram message"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    
    msg = f"✈️ **Aviation Weather for Chernihiv (UKRR)**\n"
    msg += f"📅 {timestamp}\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Temperature and humidity
    if weather and 'current' in weather:
        current = weather['current']
        temp = current.get('temperature_2m', 'N/A')
        humidity = current.get('relative_humidity_2m', 'N/A')
        msg += f"🌡 Temperature: {temp}°C\n"
        msg += f"💧 Humidity: {humidity}%\n\n"
    
    # Wind data
    if weather and 'current' in weather:
        wind_speed = current.get('wind_speed_10m', 'N/A')
        wind_dir = current.get('wind_direction_10m', None)
        wind_gust = current.get('wind_gusts_10m', None)
        
        wind_cardinal = format_wind_direction(wind_dir) if wind_dir else 'N/A'
        msg += f"💨 Wind: {wind_speed} km/h from {wind_cardinal} ({wind_dir}°)\n"
        if wind_gust:
            msg += f"💨 Gusts: {wind_gust} km/h\n"
        msg += "\n"
    
    # Cloud data from METAR
    if metar:
        msg += f"☁️ **Clouds (METAR):**\n"
        clouds = parse_clouds_from_metar(metar.get('rawOb', ''))
        msg += f"{clouds}\n\n"
    
    # Cloud cover percentage
    if weather and 'current' in weather:
        cloud_cover = current.get('cloud_cover', 'N/A')
        msg += f"☁️ Cloud Cover: {cloud_cover}%\n\n"
    
    # Visibility and pressure
    if weather and 'current' in weather:
        visibility = current.get('visibility', 'N/A')
        pressure = current.get('pressure_msl', 'N/A')
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