"""Flight data.

Positions come from OpenSky (or adsb.lol as a fallback). Airline, flight number,
origin and destination come from adsbdb, looked up once per callsign and cached.
A background thread does all the network work, so browser requests are instant
and several open tabs never multiply API calls.
"""
import logging
import math
import threading
import time

import requests

import config

log = logging.getLogger("flights")

M_TO_FT = 3.28084
MS_TO_KT = 1.94384
MS_TO_FPM = 196.85
MI_TO_NM = 0.868976


def haversine_mi(lat1, lon1, lat2, lon2):
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bbox(lat, lon, radius_mi):
    dlat = radius_mi / 69.0
    dlon = radius_mi / (69.0 * math.cos(math.radians(lat)))
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


# ---------------------------------------------------------------- positions

class OpenSkyClient:
    TOKEN_URL = ("https://auth.opensky-network.org/auth/realms/opensky-network/"
                 "protocol/openid-connect/token")
    API_URL = "https://opensky-network.org/api/states/all"

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None
        self._expires = 0.0

    def _headers(self):
        if not self.client_id or not self.client_secret:
            return {}  # anonymous: works, but with a tiny daily quota
        if time.time() > self._expires - 30:
            r = requests.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=10,
            )
            r.raise_for_status()
            body = r.json()
            self._token = body["access_token"]
            self._expires = time.time() + body.get("expires_in", 1800)
        return {"Authorization": f"Bearer {self._token}"}

    def fetch(self, lat, lon, radius_mi):
        lamin, lomin, lamax, lomax = bbox(lat, lon, radius_mi)
        r = requests.get(
            self.API_URL,
            params={"lamin": lamin, "lomin": lomin, "lamax": lamax, "lomax": lomax},
            headers=self._headers(),
            timeout=15,
        )
        r.raise_for_status()
        out = []
        for s in r.json().get("states") or []:
            if s[5] is None or s[6] is None:
                continue
            alt_m = s[13] if s[13] is not None else s[7]
            out.append({
                "icao24": s[0],
                "callsign": (s[1] or "").strip(),
                "lat": s[6],
                "lon": s[5],
                "alt_ft": round(alt_m * M_TO_FT) if alt_m is not None else None,
                "speed_kt": round(s[9] * MS_TO_KT) if s[9] is not None else None,
                "heading": s[10],
                "vrate_fpm": round(s[11] * MS_TO_FPM) if s[11] is not None else None,
                "on_ground": bool(s[8]),
            })
        return out


def fetch_adsblol(lat, lon, radius_mi):
    nm = min(250, max(1, radius_mi * MI_TO_NM))
    r = requests.get(f"https://api.adsb.lol/v2/point/{lat}/{lon}/{nm:.0f}", timeout=15)
    r.raise_for_status()
    out = []
    for a in r.json().get("ac") or []:
        if a.get("lat") is None or a.get("lon") is None:
            continue
        alt = a.get("alt_baro")
        on_ground = alt == "ground"
        out.append({
            "icao24": a.get("hex", ""),
            "callsign": (a.get("flight") or "").strip(),
            "lat": a["lat"],
            "lon": a["lon"],
            "alt_ft": None if on_ground or not isinstance(alt, (int, float)) else round(alt),
            "speed_kt": round(a["gs"]) if a.get("gs") is not None else None,
            "heading": a.get("track"),
            "vrate_fpm": a.get("baro_rate"),
            "on_ground": on_ground,
        })
    return out


# ------------------------------------------------------------------- routes

def parse_route(payload):
    """Pull airline, flight number and endpoints out of an adsbdb response."""
    resp = payload.get("response")
    if not isinstance(resp, dict):
        return None  # adsbdb returns a plain string for unknown callsigns
    fr = resp.get("flightroute")
    if not isinstance(fr, dict):
        return None

    def airport(a):
        a = a or {}
        return {
            "iata": a.get("iata_code"),
            "icao": a.get("icao_code"),
            "city": a.get("municipality"),
            "name": a.get("name"),
            "lat": a.get("latitude"),
            "lon": a.get("longitude"),
        }

    airline = fr.get("airline") or {}
    return {
        "airline": airline.get("name"),
        "flight_number": fr.get("callsign_iata") or fr.get("callsign"),
        "origin": airport(fr.get("origin")),
        "destination": airport(fr.get("destination")),
    }


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(x, y)) % 360


def angle_diff(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


# US flight numbers get reused across regional-carrier codeshares for different
# city pairs each season, so adsbdb's callsign lookup (a static community route
# database, not a live flight plan) is right well under half the time for US
# domestic flights. Catch the obviously-wrong ones by checking whether the
# aircraft is actually heading toward the claimed destination and roughly on
# the path between the claimed origin and destination.
HEADING_TOLERANCE_DEG = 90
SKIP_HEADING_CHECK_WITHIN_MI = 20  # near an airport, departure/approach patterns turn away from the direct bearing
PATH_DETOUR_SLACK = 1.6


def route_is_plausible(aircraft, route):
    dest = route.get("destination") or {}
    dlat, dlon = dest.get("lat"), dest.get("lon")
    if dlat is None or dlon is None:
        return True  # nothing to check against

    dist_to_dest = haversine_mi(aircraft["lat"], aircraft["lon"], dlat, dlon)

    origin = route.get("origin") or {}
    olat, olon = origin.get("lat"), origin.get("lon")
    dist_to_origin = (
        haversine_mi(aircraft["lat"], aircraft["lon"], olat, olon)
        if olat is not None and olon is not None else None
    )
    near_an_airport = dist_to_dest < SKIP_HEADING_CHECK_WITHIN_MI or (
        dist_to_origin is not None and dist_to_origin < SKIP_HEADING_CHECK_WITHIN_MI
    )

    heading = aircraft.get("heading")
    if heading is not None and not near_an_airport:
        bearing = bearing_deg(aircraft["lat"], aircraft["lon"], dlat, dlon)
        if angle_diff(heading, bearing) > HEADING_TOLERANCE_DEG:
            return False

    if olat is not None and olon is not None:
        direct = haversine_mi(olat, olon, dlat, dlon)
        via_aircraft = haversine_mi(olat, olon, aircraft["lat"], aircraft["lon"]) + dist_to_dest
        if direct > 1 and via_aircraft > direct * PATH_DETOUR_SLACK:
            return False

    return True


def infer_anchor_endpoint(aircraft, anchors):
    """Infer one endpoint (origin or destination) from an aircraft's position,
    altitude, vertical rate and heading relative to a known nearby airport.
    Returns (side, airport) or None. Conservative on purpose: level flight,
    cruise altitude, or a heading that does not line up gets no inference.
    """
    alt = aircraft.get("alt_ft")
    vrate = aircraft.get("vrate_fpm")
    heading = aircraft.get("heading")
    if alt is None or vrate is None or heading is None or alt > config.ANCHOR_MAX_ALT_FT:
        return None

    candidates = sorted(
        (haversine_mi(aircraft["lat"], aircraft["lon"], alat, alon), iata, name, city, alat, alon)
        for iata, name, city, alat, alon in anchors
        if haversine_mi(aircraft["lat"], aircraft["lon"], alat, alon) <= config.ANCHOR_RADIUS_MI
    )

    for _, iata, name, city, alat, alon in candidates:
        airport = {"iata": iata, "icao": None, "name": name, "city": city, "lat": alat, "lon": alon}
        if vrate <= -config.ANCHOR_VRATE_FPM:
            bearing_to_airport = bearing_deg(aircraft["lat"], aircraft["lon"], alat, alon)
            if angle_diff(heading, bearing_to_airport) <= config.ANCHOR_ARRIVAL_HEADING_TOLERANCE_DEG:
                return "destination", airport
        elif vrate >= config.ANCHOR_VRATE_FPM:
            bearing_from_airport = bearing_deg(alat, alon, aircraft["lat"], aircraft["lon"])
            if angle_diff(heading, bearing_from_airport) <= config.ANCHOR_DEPARTURE_BEARING_TOLERANCE_DEG:
                return "origin", airport
    return None


class RouteCache:
    FOUND_TTL = 24 * 3600
    MISS_TTL = 3600
    ERROR_TTL = 60

    def __init__(self):
        self._items = {}  # callsign -> (expires_at, route or None)

    def peek(self, callsign):
        """Returns (is_cached, route)."""
        item = self._items.get(callsign)
        if item and item[0] > time.time():
            return True, item[1]
        return False, None

    def fetch(self, callsign):
        try:
            r = requests.get(f"https://api.adsbdb.com/v0/callsign/{callsign}", timeout=10)
            route = None if r.status_code == 404 else parse_route(r.json())
            ttl = self.FOUND_TTL if route else self.MISS_TTL
            if r.status_code >= 500 or r.status_code == 429:
                route, ttl = None, self.ERROR_TTL
        except (requests.RequestException, ValueError) as exc:
            log.warning("route lookup failed for %s: %s", callsign, exc)
            route, ttl = None, self.ERROR_TTL
        self._items[callsign] = (time.time() + ttl, route)
        return route


# ---------------------------------------------------------------- aircraft

def combine_aircraft_type(manufacturer, type_):
    manufacturer = (manufacturer or "").strip()
    type_ = (type_ or "").strip()
    if not manufacturer:
        return type_ or None
    if not type_:
        return manufacturer or None
    manu_words = {w.lower() for w in manufacturer.split()}
    if type_.split()[0].lower() in manu_words:
        return type_  # adsbdb's type string already starts with the manufacturer name
    return f"{manufacturer} {type_}"


def parse_aircraft(payload):
    """Pull type and registered owner out of an adsbdb aircraft response."""
    resp = payload.get("response")
    if not isinstance(resp, dict):
        return None  # adsbdb returns a plain string for an unknown icao24
    a = resp.get("aircraft")
    if not isinstance(a, dict):
        return None
    return {
        "aircraft_type": combine_aircraft_type(a.get("manufacturer"), a.get("type")),
        "registered_owner": a.get("registered_owner") or None,
    }


class AircraftCache:
    FOUND_TTL = 30 * 24 * 3600
    MISS_TTL = 3600
    ERROR_TTL = 60

    def __init__(self):
        self._items = {}  # icao24 -> (expires_at, aircraft or None)

    def peek(self, icao24):
        """Returns (is_cached, aircraft)."""
        item = self._items.get(icao24)
        if item and item[0] > time.time():
            return True, item[1]
        return False, None

    def fetch(self, icao24):
        try:
            r = requests.get(f"https://api.adsbdb.com/v0/aircraft/{icao24}", timeout=10)
            aircraft = None if r.status_code == 404 else parse_aircraft(r.json())
            ttl = self.FOUND_TTL if aircraft else self.MISS_TTL
            if r.status_code >= 500 or r.status_code == 429:
                aircraft, ttl = None, self.ERROR_TTL
        except (requests.RequestException, ValueError) as exc:
            log.warning("aircraft lookup failed for %s: %s", icao24, exc)
            aircraft, ttl = None, self.ERROR_TTL
        self._items[icao24] = (time.time() + ttl, aircraft)
        return aircraft


# ------------------------------------------------------------------ tracker

class FlightTracker:
    def __init__(self):
        self.routes = RouteCache()
        self.aircraft = AircraftCache()
        self.opensky = OpenSkyClient(config.OPENSKY_CLIENT_ID, config.OPENSKY_CLIENT_SECRET)
        self._lock = threading.Lock()
        self._snapshot = {"updated": 0.0, "source": None, "error": None, "flights": []}
        self._cycle = 0

    def start(self):
        threading.Thread(target=self._run, name="flight-poller", daemon=True).start()

    def snapshot(self):
        with self._lock:
            snap = dict(self._snapshot)
        snap["age_s"] = round(time.time() - snap["updated"], 1) if snap["updated"] else None
        snap["home"] = {"lat": config.HOME_LAT, "lon": config.HOME_LON}
        return snap

    def _fetch_positions(self):
        sources = [
            ("opensky", lambda: self.opensky.fetch(config.HOME_LAT, config.HOME_LON, config.RADIUS_MI)),
            ("adsblol", lambda: fetch_adsblol(config.HOME_LAT, config.HOME_LON, config.RADIUS_MI)),
        ]
        if config.FLIGHT_SOURCE == "adsblol":
            sources.reverse()
        last_exc = None
        for name, fn in sources:
            try:
                return name, fn()
            except Exception as exc:  # try the next source
                log.warning("%s failed: %s", name, exc)
                last_exc = exc
        raise last_exc

    def _build(self, aircraft):
        flights = []
        for a in aircraft:
            if a["on_ground"] and not config.SHOW_GROUND_TRAFFIC:
                continue
            dist = haversine_mi(config.HOME_LAT, config.HOME_LON, a["lat"], a["lon"])
            if dist > config.RADIUS_MI:
                continue
            flights.append({**a, "distance_mi": round(dist, 1)})
        flights.sort(key=lambda f: f["distance_mi"])

        route_lookups = 0
        aircraft_lookups = 0
        counts = {"full": 0, "inferred": 0, "none": 0, "rejected": 0}
        for f in flights:
            cs = f["callsign"]
            route = None
            if cs:
                cached, route = self.routes.peek(cs)
                if not cached and route_lookups < config.MAX_ROUTE_LOOKUPS_PER_CYCLE:
                    route = self.routes.fetch(cs)
                    route_lookups += 1
            # Airline name and flight number come from static callsign/ICAO
            # lookups and stay reliable even when the route does not; only the
            # origin/destination (keyed by the reused flight number) need the
            # plausibility check.
            f["airline"] = route["airline"] if route else None
            f["flight_number"] = (route and route["flight_number"]) or cs or f["icao24"]

            route_ok = bool(route) and route_is_plausible(f, route)
            if route and not route_ok:
                counts["rejected"] += 1
            origin = route["origin"] if route_ok else None
            destination = route["destination"] if route_ok else None
            confidence = "full" if route_ok else "none"

            anchor = infer_anchor_endpoint(f, config.AIRPORT_ANCHORS)
            if anchor:
                side, airport = anchor
                current = origin if side == "origin" else destination
                if not (current and current.get("iata") == airport["iata"]):
                    # Route is missing, implausible, or contradicts the inference:
                    # drop both of its endpoints rather than mix a confirmed one
                    # with an inferred one.
                    origin = airport if side == "origin" else None
                    destination = airport if side == "destination" else None
                    confidence = "inferred"

            f["origin"] = origin
            f["destination"] = destination
            f["route_confidence"] = confidence
            counts[confidence] += 1

            icao24 = f["icao24"]
            cached, aircraft_info = self.aircraft.peek(icao24)
            if not cached and aircraft_lookups < config.MAX_AIRCRAFT_LOOKUPS_PER_CYCLE:
                aircraft_info = self.aircraft.fetch(icao24)
                aircraft_lookups += 1
            f["aircraft_type"] = aircraft_info["aircraft_type"] if aircraft_info else None
            f["registered_owner"] = aircraft_info["registered_owner"] if aircraft_info else None

        self._cycle += 1
        if self._cycle % 10 == 0:
            log.info(
                "route summary (last cycle): full=%d inferred=%d none=%d rejected=%d",
                counts["full"], counts["inferred"], counts["none"], counts["rejected"],
            )
        return flights

    def _run(self):
        while True:
            delay = config.POLL_SECONDS
            try:
                source, aircraft = self._fetch_positions()
                flights = self._build(aircraft)
                with self._lock:
                    self._snapshot = {
                        "updated": time.time(),
                        "source": source,
                        "error": None,
                        "flights": flights,
                    }
                log.info("%s: %d aircraft in range", source, len(flights))
            except Exception as exc:
                log.error("poll failed: %s", exc)
                with self._lock:
                    self._snapshot = {**self._snapshot, "error": str(exc)}
                delay = max(delay * 2, 60)
            time.sleep(delay)
