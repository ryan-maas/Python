"""All settings in one place. Values come from .env (see .env.example)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _float(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def _list(name, default):
    raw = os.getenv(name, default)
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


# Location
HOME_LAT = _float("HOME_LAT", 30.427749633789062)
HOME_LON = _float("HOME_LON", -97.72123718261719)
RADIUS_MI = _float("RADIUS_MI", 20)
TIMEZONE = os.getenv("TIMEZONE", "America/Chicago")

# Flights
OPENSKY_CLIENT_ID = os.getenv("OPENSKY_CLIENT_ID", "")
OPENSKY_CLIENT_SECRET = os.getenv("OPENSKY_CLIENT_SECRET", "")
FLIGHT_SOURCE = os.getenv("FLIGHT_SOURCE", "opensky").lower()
POLL_SECONDS = max(10.0, _float("POLL_SECONDS", 30))
MAX_ROUTE_LOOKUPS_PER_CYCLE = 6
MAX_AIRCRAFT_LOOKUPS_PER_CYCLE = 6
SHOW_GROUND_TRAFFIC = False
CARTO_KEY = os.getenv("CARTO_KEY", "")

# Airport-anchored route inference: adsbdb's route-by-callsign lookup is often
# wrong for US domestic flights (see route_is_plausible in sources/flights.py),
# so nearby traffic that is clearly arriving at or departing from a known local
# airport gets a lower-confidence inferred endpoint instead of nothing.
# (iata, name, city, lat, lon). Home is near Austin-Bergstrom; add more airports
# here later if useful.
AIRPORT_ANCHORS = [
    ("AUS", "Austin-Bergstrom International Airport", "Austin", 30.1945, -97.6699),
]
ANCHOR_RADIUS_MI = 30
ANCHOR_MAX_ALT_FT = 15000  # tuned up from 12000: live traffic showed clean, well-aligned
# departures/arrivals still climbing or descending through 12000-15000 ft at this range
ANCHOR_VRATE_FPM = 300  # matches the "climbing"/"descending" threshold already used in map.js
ANCHOR_ARRIVAL_HEADING_TOLERANCE_DEG = 60
ANCHOR_DEPARTURE_BEARING_TOLERANCE_DEG = 90

# Map and rotation (sent to the browser)
MAP_ZOOM = _float("MAP_ZOOM", 11)
ALERT_MI = _float("ALERT_MI", 5)  # jump to the map when a plane gets this close
CLIENT_POLL_MS = 10_000
AUTO_RELOAD = os.getenv("AUTO_RELOAD", "true").strip().lower() not in ("0", "false", "no", "off")
VERSION_POLL_SECONDS = 30  # how often the page checks /api/version for a new deploy

# Calendar
ICAL_URL = os.getenv("ICAL_URL", "")
# Your address is read from ICAL_URL. List extra addresses or aliases here (comma-separated)
# so events you declined under them are hidden too.
CALENDAR_EMAILS = [s.strip() for s in os.getenv("CALENDAR_EMAILS", "").split(",") if s.strip()]
CALENDAR_DAYS = 7
CALENDAR_TTL = 300

# Stocks
FINNHUB_KEY = os.getenv("FINNHUB_KEY", "")
STOCK_SYMBOLS = _list("STOCK_SYMBOLS", "SPY,QQQ,DIA,AAPL,MSFT,NVDA")
STOCKS_TTL = 60

# Weather (Open-Meteo, no key needed)
WEATHER_TTL = 600
WEATHER_HOURS = 12

# News (RSS, blended with Finnhub for markets)
NEWS_TTL = 300
NEWS_MAX_ITEMS = 8
NEWS_MAX_AGE_HOURS = 48
NEWS_MAX_PER_SOURCE = 4

NEWS_GENERAL_FEEDS = [
    ("NPR", "https://feeds.npr.org/1001/rss.xml"),
    # ("BBC", "https://feeds.bbci.co.uk/news/rss.xml"),
]
NEWS_MARKETS_FEEDS = [
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("CNBC Finance", "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
    ("MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
    # MarketWatch's marketpulse feed is dead (newest item was over a year old), dropped.
]

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))
