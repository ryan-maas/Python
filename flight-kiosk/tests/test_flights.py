"""Smoke tests for the airport-anchored route inference and aircraft lookups in
sources/flights.py. No network: requests.get is mocked. Run with:
  python3 -m unittest discover tests
"""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from sources import flights

AUS_IATA, _AUS_NAME, AUS_CITY, AUS_LAT, AUS_LON = config.AIRPORT_ANCHORS[0]


def make_aircraft(lat, lon, heading, vrate, alt=4000, icao24="abc123", callsign="TEST1"):
    return {
        "icao24": icao24, "callsign": callsign, "lat": lat, "lon": lon,
        "alt_ft": alt, "speed_kt": 200, "heading": heading, "vrate_fpm": vrate,
        "on_ground": False,
    }


class InferAnchorEndpointTests(unittest.TestCase):
    def test_arrival_descending_toward_aus(self):
        lat, lon = AUS_LAT - 0.2, AUS_LON  # south of the airport
        heading = flights.bearing_deg(lat, lon, AUS_LAT, AUS_LON)  # pointed at it
        ac = make_aircraft(lat, lon, heading, vrate=-1500)
        result = flights.infer_anchor_endpoint(ac, config.AIRPORT_ANCHORS)
        self.assertEqual(result, ("destination", {
            "iata": AUS_IATA, "icao": None, "name": _AUS_NAME, "city": AUS_CITY,
            "lat": AUS_LAT, "lon": AUS_LON,
        }))

    def test_departure_climbing_away_from_aus(self):
        lat, lon = AUS_LAT + 0.2, AUS_LON  # north of the airport, continuing north
        heading = flights.bearing_deg(AUS_LAT, AUS_LON, lat, lon)  # radial outbound
        ac = make_aircraft(lat, lon, heading, vrate=1500)
        result = flights.infer_anchor_endpoint(ac, config.AIRPORT_ANCHORS)
        self.assertIsNotNone(result)
        side, airport = result
        self.assertEqual(side, "origin")
        self.assertEqual(airport["iata"], AUS_IATA)

    def test_level_flight_gets_no_inference(self):
        lat, lon = AUS_LAT - 0.2, AUS_LON
        heading = flights.bearing_deg(lat, lon, AUS_LAT, AUS_LON)
        ac = make_aircraft(lat, lon, heading, vrate=0)  # not climbing or descending
        self.assertIsNone(flights.infer_anchor_endpoint(ac, config.AIRPORT_ANCHORS))

    def test_cruise_altitude_overflight_gets_no_inference(self):
        lat, lon = AUS_LAT - 0.1, AUS_LON
        heading = flights.bearing_deg(lat, lon, AUS_LAT, AUS_LON)
        ac = make_aircraft(lat, lon, heading, vrate=-1500, alt=35000)
        self.assertIsNone(flights.infer_anchor_endpoint(ac, config.AIRPORT_ANCHORS))

    def test_heading_away_from_airport_blocks_arrival(self):
        lat, lon = AUS_LAT - 0.2, AUS_LON  # south of AUS, descending
        ac = make_aircraft(lat, lon, heading=180, vrate=-1500)  # heading further south, away
        self.assertIsNone(flights.infer_anchor_endpoint(ac, config.AIRPORT_ANCHORS))

    def test_far_from_any_anchor_gets_no_inference(self):
        ac = make_aircraft(32.7767, -96.7970, heading=180, vrate=-1500)  # Dallas, ~200 mi away
        self.assertIsNone(flights.infer_anchor_endpoint(ac, config.AIRPORT_ANCHORS))


class BuildCombinesRouteAndInferenceTests(unittest.TestCase):
    def setUp(self):
        self.tracker = flights.FlightTracker()

    def _seed_route(self, callsign, route):
        self.tracker.routes._items[callsign] = (time.time() + 3600, route)

    def _seed_aircraft(self, icao24, info):
        self.tracker.aircraft._items[icao24] = (time.time() + 3600, info)

    def test_contradicting_but_plausible_route_is_discarded_for_inferred(self):
        lat, lon = AUS_LAT + 0.1, AUS_LON  # north of AUS (inside RADIUS_MI of home), inbound
        heading = flights.bearing_deg(lat, lon, AUS_LAT, AUS_LON)
        ac = make_aircraft(lat, lon, heading, vrate=-1500, icao24="c0ffee", callsign="DAL381")
        route = {
            "airline": "Delta Air Lines", "flight_number": "DL381",
            "origin": {"iata": "SLC", "icao": "KSLC", "city": "Salt Lake City", "name": "SLC Intl",
                       "lat": 40.7899, "lon": -111.9791},
            # destination placed right on top of the aircraft so route_is_plausible
            # passes it (the near-an-airport exemption skips the heading check),
            # even though it is a different airport than where the plane is headed.
            "destination": {"iata": "ZZZ", "icao": "KZZZ", "city": "Nowhere", "name": "Fake Intl",
                             "lat": lat, "lon": lon},
        }
        self._seed_route("DAL381", route)
        self._seed_aircraft("c0ffee", None)

        out = self.tracker._build([ac])
        self.assertEqual(len(out), 1)
        f = out[0]
        self.assertEqual(f["route_confidence"], "inferred")
        self.assertEqual(f["destination"]["iata"], AUS_IATA)
        self.assertIsNone(f["origin"])  # the route's other end must not leak through

    def test_plausible_route_matching_inference_is_kept_full(self):
        lat, lon = AUS_LAT + 0.1, AUS_LON  # north of AUS (inside RADIUS_MI of home), inbound
        heading = flights.bearing_deg(lat, lon, AUS_LAT, AUS_LON)
        ac = make_aircraft(lat, lon, heading, vrate=-1500, icao24="aaaaaa", callsign="SWA100")
        route = {
            "airline": "Southwest Airlines", "flight_number": "WN100",
            "origin": {"iata": "DAL", "icao": "KDAL", "city": "Dallas", "name": "Love Field",
                       "lat": 32.8471, "lon": -96.8518},
            "destination": {"iata": AUS_IATA, "icao": "KAUS", "city": AUS_CITY, "name": _AUS_NAME,
                             "lat": AUS_LAT, "lon": AUS_LON},
        }
        self._seed_route("SWA100", route)
        self._seed_aircraft("aaaaaa", None)

        out = self.tracker._build([ac])
        f = out[0]
        self.assertEqual(f["route_confidence"], "full")
        self.assertEqual(f["origin"]["iata"], "DAL")
        self.assertEqual(f["destination"]["iata"], AUS_IATA)

    def test_no_route_no_inference_is_none(self):
        # within RADIUS_MI of home (so _build keeps it) but level, so no inference applies
        ac = make_aircraft(config.HOME_LAT, config.HOME_LON, heading=180, vrate=0,
                            icao24="bbbbbb", callsign="UNK1")
        self._seed_route("UNK1", None)
        self._seed_aircraft("bbbbbb", None)

        out = self.tracker._build([ac])
        f = out[0]
        self.assertEqual(f["route_confidence"], "none")
        self.assertIsNone(f["origin"])
        self.assertIsNone(f["destination"])

    def test_aircraft_type_and_owner_attached_when_known(self):
        ac = make_aircraft(config.HOME_LAT, config.HOME_LON, heading=180, vrate=0,
                            icao24="cccccc", callsign="UNK2")
        self._seed_route("UNK2", None)
        self._seed_aircraft("cccccc", {"aircraft_type": "Boeing 737-800", "registered_owner": "United Airlines"})

        out = self.tracker._build([ac])
        f = out[0]
        self.assertEqual(f["aircraft_type"], "Boeing 737-800")
        self.assertEqual(f["registered_owner"], "United Airlines")


class CombineAircraftTypeTests(unittest.TestCase):
    def test_combines_manufacturer_and_type(self):
        self.assertEqual(flights.combine_aircraft_type("Boeing", "737-800"), "Boeing 737-800")

    def test_avoids_duplicating_leading_word(self):
        self.assertEqual(flights.combine_aircraft_type("Boeing", "Boeing 737-800"), "Boeing 737-800")

    def test_handles_missing_pieces(self):
        self.assertEqual(flights.combine_aircraft_type("", "737-800"), "737-800")
        self.assertEqual(flights.combine_aircraft_type("Boeing", ""), "Boeing")
        self.assertIsNone(flights.combine_aircraft_type("", ""))


class AircraftCacheTtlTests(unittest.TestCase):
    def test_found_is_cached_for_30_days(self):
        cache = flights.AircraftCache()
        payload = {"response": {"aircraft": {"manufacturer": "Boeing", "type": "737-800",
                                              "registered_owner": "United Airlines"}}}
        resp = Mock(status_code=200, json=lambda: payload)
        with patch("sources.flights.requests.get", return_value=resp):
            result = cache.fetch("abc123")
        self.assertEqual(result["aircraft_type"], "Boeing 737-800")
        expires_at, cached = cache._items["abc123"]
        self.assertAlmostEqual(expires_at - time.time(), flights.AircraftCache.FOUND_TTL, delta=2)
        self.assertEqual(cached, result)

    def test_unknown_icao24_is_cached_for_one_hour(self):
        cache = flights.AircraftCache()
        resp = Mock(status_code=404)
        with patch("sources.flights.requests.get", return_value=resp):
            result = cache.fetch("deadbeef")
        self.assertIsNone(result)
        expires_at, cached = cache._items["deadbeef"]
        self.assertAlmostEqual(expires_at - time.time(), flights.AircraftCache.MISS_TTL, delta=2)
        self.assertIsNone(cached)

    def test_error_is_cached_for_60_seconds(self):
        cache = flights.AircraftCache()
        with patch("sources.flights.requests.get", side_effect=flights.requests.RequestException("boom")):
            result = cache.fetch("badhex")
        self.assertIsNone(result)
        expires_at, cached = cache._items["badhex"]
        self.assertAlmostEqual(expires_at - time.time(), flights.AircraftCache.ERROR_TTL, delta=2)


if __name__ == "__main__":
    unittest.main()
