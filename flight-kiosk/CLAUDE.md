# Desk flight tracker kiosk

## What this is
A Flask server plus a single-page web UI that runs full screen in Chromium kiosk
mode on a Raspberry Pi 5 (4GB) with the official Raspberry Pi Touch Display 2
(10.1", natively portrait 1200x1920, rotated to landscape in the OS). It rotates
through scenes: a live flight map, calendar, markets, news, and weather. I develop on a
Mac laptop first, then deploy to the Pi. The Pi hardware is arriving soon and is
not set up yet.

## Core requirement
The flight map shows planes near my home in Austin, TX. Each plane is labeled with
airline, flight number, origin, and destination. There is also a side board
listing the nearest aircraft.

## Stack and layout
- Python 3 / Flask backend, vanilla JS frontend, Leaflet map, no build step.
- `app.py`: Flask routes (`/api/config`, `/api/flights`, `/api/calendar`,
  `/api/stocks`, `/api/news`, `/api/weather`, `/api/version`) and static file
  serving (sent with `Cache-Control: no-cache`). Calls
  `app.run` with `use_reloader=False` so the background poller starts only once.
- `config.py`: all settings, loaded from `.env` (see `.env.example`).
- `sources/flights.py`: a background thread polls OpenSky (OAuth2 client
  credentials) and falls back to adsb.lol automatically. Routes (airline, flight
  number, origin, destination) come from adsbdb by callsign, cached (24h for
  hits, 1h for misses, 60s on errors) with a cap on new lookups per cycle.
  `route_is_plausible()` rejects adsbdb routes whose heading/path do not match
  the aircraft (adsbdb's route-by-callsign lookup is often wrong for US domestic
  flights). When a route is missing, implausible, or contradicts where the
  aircraft is clearly arriving/departing near a known local airport
  (`AIRPORT_ANCHORS` in config.py, just AUS for now), `infer_anchor_endpoint()`
  supplies a lower-confidence single endpoint instead. Each flight carries
  `route_confidence`: "full", "inferred", or "none". Aircraft type and
  registered owner come from a separate adsbdb lookup by icao24, cached 30 days
  (1h misses, 60s errors), with its own per-cycle lookup cap. A summary of
  full/inferred/none/rejected counts is logged every 10 poll cycles, not per flight.
- `sources/gcal.py`: Google Calendar via the secret iCal URL (no OAuth), using
  `icalendar` and `recurring-ical-events`. Named gcal to avoid shadowing the
  stdlib `calendar` module. Hides instances I declined (PARTSTAT=DECLINED on my
  ATTENDEE entry); my address comes from the ICAL_URL path plus optional
  `CALENDAR_EMAILS`. Never log ICAL_URL (secret token); fetch errors are redacted.
- `sources/stocks.py`: Finnhub quotes (ETFs only, since free tier has no index levels).
- `sources/news.py`: RSS headlines (NPR for general, CNBC and MarketWatch for
  markets), blended with Finnhub market news if `FINNHUB_KEY` is set. Each feed
  is fetched independently so one dead feed does not hide the others; items
  older than `NEWS_MAX_AGE_HOURS` are dropped, near-duplicate titles removed,
  capped per source so one outlet cannot dominate a column. If the cap leaves a
  column short of `NEWS_MAX_ITEMS` (Top stories has only NPR), it backfills from
  the remaining items newest first.
- `sources/weather.py`: Open-Meteo, no key. Current conditions, 5-day daily,
  and an hourly strip (`WEATHER_HOURS` hours starting at the current local hour,
  via Open-Meteo's `forecast_hours` param, confirmed it already starts there).
- `static/index.html`, `style.css`, `map.js` (markers that glide between polls by
  projecting along heading and speed), `app.js` (clock, scene rotation, calendar,
  stocks, news, weather panes, jump-to-map when a plane comes within `ALERT_MI`).

## Design decisions to preserve
- The server polls upstream APIs on a timer; the browser only reads the server's
  cached snapshot. Keep it that way so open tabs never multiply API calls.
- Poll interval defaults to 30s because of OpenSky's free-tier daily credit limit.
  I have not verified the current limit, so check before lowering `POLL_SECONDS`.
- Scenes are hidden with opacity, not `display: none`, so Leaflet keeps its size.
- All API text is escaped before going into innerHTML. Keep that.
- Missing keys must produce a plain on-screen message, never break the rotation.
- UI sizing scales from `html { font-size: 28px }` in `style.css`, tuned for a
  dense 10.1" panel at roughly 1920x1200 landscape. Expect to adjust once on the device.
- Visual direction: dark navy base, amber for aircraft, Barlow / Barlow Condensed
  type, departure-board style rows. Avoid generic template styling.
- Avoid em dashes in prose, comments, and UI copy.

## Environment and gotchas
- On macOS, port 5000 is taken by AirPlay Receiver, so I run with `PORT=5001` in `.env`.
- Config is in `.env` (never commit it): OpenSky client id/secret, `ICAL_URL`,
  `FINNHUB_KEY`, `STOCK_SYMBOLS`, `CARTO_KEY`, `PORT`.
- CARTO now requires a free API key for basemap tiles, otherwise tiles come back
  with an "API KEY REQUIRED" watermark. The key is passed via `/api/config` as
  `carto_key` and appended to the tile URL as `?key=...` in `map.js`. Whether the
  `dark_all` path accepts the key in this form is unverified. Keyless fallback
  option: Esri World_Dark_Gray_Base raster tiles (also untested).
- `STOCK_SYMBOLS` I plan to use: SPY,QQQ,DIA,IWM,VTI,VXUS,AGG,TLT

## Current status
- Backend logic and API endpoints were smoke-tested with mocked data only.
- Not yet verified with live data: OpenSky auth and polling, adsbdb route
  lookups, real plane labels on the map, calendar parsing of my real calendar,
  Finnhub quotes for every symbol.
- Map tiles: switching to a keyed CARTO URL (just done, needs confirming).
- Auto-reload: the page polls `/api/version` every `VERSION_POLL_SECONDS` (30)
  and reloads when it changes (hash of static/ contents plus server start time,
  so a deploy or a restart both trigger it). Guarded to one reload per 30s via
  sessionStorage. Disable with `AUTO_RELOAD=false`. Verified locally in headless Chrome.
- Flight radius default is now 20 miles (`RADIUS_MI`). The ring fits at
  `MAP_ZOOM` 11 at 1920x1200 with about 75px to spare top and bottom. The Pi's
  own `.env` needs `RADIUS_MI=20` set by hand.
- Map shows a hollow muted ring plus code label for every airport in
  `AIRPORT_ANCHORS` (just AUS), sent via `/api/config` as `airports`.
- Not started: Pi setup, systemd service, Chromium kiosk launch, display
  rotation and touch rotation, a mount or stand for the panel.

## Likely next tasks
1. Confirm tiles load with the CARTO key, and fix the tile URL if not.
2. Check `/api/flights` output against real traffic, then tune label crowding,
   zoom level (`MAP_ZOOM`), and the side board.
3. Verify calendar, stocks, and weather scenes with real data.
4. Prepare for Pi deployment (see README), including a fallback if the map
   tile provider changes again.

## How to work with me
Explain changes briefly and show what you changed. Run the server and check the
API endpoints after backend edits. Ask before adding dependencies or restructuring.