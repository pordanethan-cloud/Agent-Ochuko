# app/services/weather_service.py
"""
Weather tool service — Phase 5 (tool: weather_fetch).

Keyless Open-Meteo: geocoding + forecast. Compact, model-friendly output.
No API key required; failures return readable error text the model can pivot
on (e.g. suggest the user name a larger nearby city).
"""
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT = httpx.Timeout(12.0, connect=7.0)

_WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Drizzle",
    55: "Dense drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Heavy freezing rain", 71: "Light snow",
    73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Light rain showers",
    81: "Rain showers", 82: "Violent rain showers", 85: "Snow showers",
    86: "Heavy snow showers", 95: "Thunderstorm", 96: "Thunderstorm with hail",
    99: "Severe thunderstorm with hail",
}


def _describe(code) -> str:
    try:
        return _WMO_CODES.get(int(code), f"code {code}")
    except (TypeError, ValueError):
        return "unknown"


async def fetch_weather(location_name: str, days: int = 3) -> str:
    """Geocodes the location and returns a compact current + N-day forecast."""
    location_name = (location_name or "").strip()
    if not location_name:
        return "weather_fetch error: no location provided."
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            geo = await client.get(_GEO_URL, params={
                "name": location_name, "count": 1, "language": "en", "format": "json",
            })
            geo.raise_for_status()
            results = (geo.json() or {}).get("results") or []
            if not results:
                return (
                    f"weather_fetch error: no geocoding match for {location_name!r}. "
                    "Try a larger nearby city (e.g. 'Lagos' rather than a district)."
                )
            place = results[0]
            lat, lon = place["latitude"], place["longitude"]
            label_parts = [place.get("name", location_name)]
            if place.get("admin1"):
                label_parts.append(place["admin1"])
            if place.get("country"):
                label_parts.append(place["country"])
            label = ", ".join(label_parts)

            fc = await client.get(_FORECAST_URL, params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "forecast_days": max(1, min(int(days), 7)),
                "timezone": "auto",
            })
            fc.raise_for_status()
            data = fc.json() or {}
    except httpx.HTTPError as exc:
        logger.warning("weather_fetch failed for %r: %s", location_name, exc)
        return f"weather_fetch error: request failed ({exc})"

    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    lines = [
        f"Weather for {label} (tz: {data.get('timezone', 'local')}):",
        (
            f"NOW: {_describe(cur.get('weather_code'))}, "
            f"{cur.get('temperature_2m')}°C (feels {cur.get('apparent_temperature')}°C), "
            f"humidity {cur.get('relative_humidity_2m')}%, wind {cur.get('wind_speed_10m')} km/h"
        ),
    ]
    dates = daily.get("time") or []
    codes = daily.get("weather_code") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_probability_max") or []
    for i, date in enumerate(dates[:max(1, min(int(days), 7))]):
        t_max = tmax[i] if i < len(tmax) else "?"
        t_min = tmin[i] if i < len(tmin) else "?"
        p = precip[i] if i < len(precip) else "?"
        lines.append(
            f"{date}: {_describe(codes[i] if i < len(codes) else None)}, "
            f"{t_min}–{t_max}°C, precip chance {p}%"
        )
    return "\n".join(lines)
