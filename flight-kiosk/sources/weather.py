"""Weather from Open-Meteo (free, no key)."""
import logging
import time

import requests

import config

log = logging.getLogger("weather")
_cache = {"t": 0.0, "data": None}

WMO = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 71: "Light snow", 73: "Snow",
    75: "Heavy snow", 80: "Showers", 81: "Showers", 82: "Heavy showers",
    95: "Thunderstorms", 96: "Thunderstorms with hail", 99: "Thunderstorms with hail",
}


def get_weather():
    if _cache["data"] and time.time() - _cache["t"] < config.WEATHER_TTL:
        return _cache["data"]
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": config.HOME_LAT,
                "longitude": config.HOME_LON,
                "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "hourly": "temperature_2m,precipitation_probability,weather_code",
                "forecast_hours": config.WEATHER_HOURS,
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": config.TIMEZONE,
                "forecast_days": 5,
            },
            timeout=10,
        )
        r.raise_for_status()
        j = r.json()
        cur, d, h = j["current"], j["daily"], j.get("hourly") or {}
        data = {
            "error": None,
            "current": {
                "temp": round(cur["temperature_2m"]),
                "feels_like": round(cur["apparent_temperature"]),
                "wind_mph": round(cur["wind_speed_10m"]),
                "summary": WMO.get(cur["weather_code"], "Unknown"),
            },
            "daily": [
                {
                    "date": d["time"][i],
                    "high": round(d["temperature_2m_max"][i]),
                    "low": round(d["temperature_2m_min"][i]),
                    "rain_pct": d["precipitation_probability_max"][i],
                    "summary": WMO.get(d["weather_code"][i], "Unknown"),
                }
                for i in range(len(d["time"]))
            ],
            "hourly": [
                {
                    "time": h["time"][i],
                    "temp": round(h["temperature_2m"][i]),
                    "rain_pct": h["precipitation_probability"][i],
                }
                for i in range(len(h.get("time") or []))
            ],
        }
    except Exception as exc:
        log.error("weather fetch failed: %s", exc)
        if _cache["data"]:
            return _cache["data"]
        return {"error": f"Could not load weather: {exc}"}
    _cache.update(t=time.time(), data=data)
    return data
