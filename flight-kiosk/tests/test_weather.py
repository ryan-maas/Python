"""Smoke tests for sources/weather.py's hourly forecast. No network: requests.get
is mocked. Run with:  python3 -m unittest discover tests
"""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sources import weather

CURRENT = {"temperature_2m": 77, "apparent_temperature": 79, "weather_code": 3, "wind_speed_10m": 8}
DAILY = {
    "time": ["2026-10-02"],
    "temperature_2m_max": [88],
    "temperature_2m_min": [68],
    "precipitation_probability_max": [30],
    "weather_code": [3],
}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class WeatherHourlyTests(unittest.TestCase):
    def setUp(self):
        weather._cache = {"t": 0.0, "data": None}

    def test_hourly_parsed_and_time_not_shifted(self):
        payload = {
            "current": CURRENT,
            "daily": DAILY,
            "hourly": {
                "time": ["2026-10-02T15:00", "2026-10-02T16:00", "2026-10-02T17:00"],
                "temperature_2m": [77.4, 78.1, 76.6],
                "precipitation_probability": [37, 29, None],
            },
        }
        with patch("sources.weather.requests.get", return_value=FakeResponse(payload)):
            data = weather.get_weather()

        self.assertIsNone(data["error"])
        self.assertEqual(len(data["hourly"]), 3)
        # the local wall-clock string must pass through untouched, not get
        # reparsed/reformatted (which is how a timezone shift would sneak in)
        self.assertEqual(data["hourly"][0]["time"], "2026-10-02T15:00")
        self.assertEqual(data["hourly"][1]["time"], "2026-10-02T16:00")
        self.assertEqual(data["hourly"][0]["temp"], 77)  # rounded
        self.assertEqual(data["hourly"][1]["temp"], 78)
        self.assertEqual(data["hourly"][0]["rain_pct"], 37)
        self.assertIsNone(data["hourly"][2]["rain_pct"])  # null passes through as null

    def test_missing_hourly_key_yields_empty_list(self):
        payload = {"current": CURRENT, "daily": DAILY}  # no "hourly" at all
        with patch("sources.weather.requests.get", return_value=FakeResponse(payload)):
            data = weather.get_weather()

        self.assertIsNone(data["error"])
        self.assertEqual(data["hourly"], [])

    def test_existing_fields_unaffected(self):
        payload = {"current": CURRENT, "daily": DAILY, "hourly": {"time": [], "temperature_2m": [], "precipitation_probability": []}}
        with patch("sources.weather.requests.get", return_value=FakeResponse(payload)):
            data = weather.get_weather()

        self.assertEqual(data["current"]["temp"], 77)
        self.assertEqual(len(data["daily"]), 1)
        self.assertEqual(data["hourly"], [])

    def test_stale_cache_fallback_still_works(self):
        cached = {"error": None, "current": {}, "daily": [], "hourly": []}
        weather._cache = {"t": time.time(), "data": cached}
        with patch("sources.weather.requests.get", side_effect=ConnectionError("boom")):
            # within TTL: should not even hit the network
            data = weather.get_weather()
        self.assertEqual(data, cached)


if __name__ == "__main__":
    unittest.main()
