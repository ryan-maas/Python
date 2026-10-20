"""Desk flight tracker kiosk: Flask server.

Run:  python app.py   then open http://localhost:5000
"""
import hashlib
import logging
import os
import threading
import time

from flask import Flask, jsonify, request, send_from_directory

import config
from sources import flights, gcal, news, stocks, weather

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("app")

app = Flask(__name__, static_folder="static", static_url_path="")
tracker = flights.FlightTracker()

# Mixed into the version hash so a server restart also tells open pages to reload.
_STARTED = str(time.time())
_version_cache = {"t": 0.0, "value": None}
_version_lock = threading.Lock()


def respond(fn):
    try:
        return jsonify(fn())
    except Exception as exc:
        log.exception("handler failed")
        return jsonify({"error": str(exc)}), 502


@app.after_request
def no_cache_static(resp):
    # Revalidate the page and its JS/CSS on every load so a reload never runs stale code.
    if request.path == "/" or not request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


def static_version():
    """Short hash of every file under static/ plus this process's start time,
    cached for 5 seconds so polling stays cheap."""
    with _version_lock:
        if _version_cache["value"] and time.time() - _version_cache["t"] < 5:
            return _version_cache["value"]
        h = hashlib.sha256(_STARTED.encode())
        for root, dirs, files in os.walk(app.static_folder):
            dirs.sort()
            for name in sorted(files):
                if name.startswith("."):
                    continue  # .DS_Store and friends change without a deploy
                path = os.path.join(root, name)
                h.update(os.path.relpath(path, app.static_folder).encode())
                try:
                    with open(path, "rb") as f:
                        h.update(f.read())
                except OSError:
                    pass  # file vanished mid-deploy; the next poll will catch up
        _version_cache.update(t=time.time(), value=h.hexdigest()[:12])
        return _version_cache["value"]


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/config")
def api_config():
    return jsonify({
        "home": {"lat": config.HOME_LAT, "lon": config.HOME_LON},
        "radius_mi": config.RADIUS_MI,
        "map_zoom": config.MAP_ZOOM,
        "alert_mi": config.ALERT_MI,
        "timezone": config.TIMEZONE,
        "client_poll_ms": config.CLIENT_POLL_MS,
        "carto_key": config.CARTO_KEY,
        "airports": [
            {"iata": iata, "name": name, "lat": lat, "lon": lon}
            for iata, name, _city, lat, lon in config.AIRPORT_ANCHORS
        ],
        "auto_reload": config.AUTO_RELOAD,
        "version_poll_seconds": config.VERSION_POLL_SECONDS,
    })


@app.get("/api/version")
def api_version():
    return jsonify({"version": static_version()})


@app.get("/api/flights")
def api_flights():
    return jsonify(tracker.snapshot())


@app.get("/api/calendar")
def api_calendar():
    return respond(gcal.get_events)


@app.get("/api/stocks")
def api_stocks():
    return respond(stocks.get_quotes)


@app.get("/api/weather")
def api_weather():
    return respond(weather.get_weather)


@app.get("/api/news")
def api_news():
    return respond(news.get_news)


if __name__ == "__main__":
    tracker.start()
    # use_reloader=False so the background poller only starts once
    app.run(host=config.HOST, port=config.PORT, threaded=True, use_reloader=False)
