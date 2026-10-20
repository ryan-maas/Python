# Desk flight tracker kiosk

A Flask server plus a single web page that rotates through scenes: a live flight map
(with airline, flight number, origin and destination), calendar, markets, news, and weather.

## Run it on your laptop first

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env        # then fill in your keys
    python app.py

Open http://localhost:5000. To preview the Pi display, make the browser window
1920x1200 (or use dev tools device mode). The page is built for landscape.

Check the raw data any time:

    http://localhost:5000/api/flights
    http://localhost:5000/api/calendar
    http://localhost:5000/api/stocks
    http://localhost:5000/api/news
    http://localhost:5000/api/weather

## What needs keys

| Scene     | Needs                                              |
|-----------|----------------------------------------------------|
| Flights   | OpenSky API client id and secret (adsb.lol fallback needs nothing) |
| Calendar  | Secret iCal address in ICAL_URL                    |
| Markets   | Finnhub key in FINNHUB_KEY                         |
| News      | Nothing (RSS only). Finnhub key in FINNHUB_KEY adds more market headlines if set |
| Weather   | Nothing                                            |

Any scene without its key shows a plain message instead of breaking the rotation.

## Tuning

* `config.py`: radius (20 miles by default), poll rate, map zoom, how close a plane must be to pull the display to the map.
* `AIRPORT_ANCHORS` in `config.py`: airports drawn on the map (AUS by default). Add a row to show another one.
* `CALENDAR_EMAILS` in `.env`: extra addresses or aliases, so events you declined under them are hidden. Your main address is read from `ICAL_URL`.
* `AUTO_RELOAD` in `.env`: the page reloads itself within about 30 seconds of a deploy or server restart. Set it to `false` to turn that off.
* `static/app.js`: the `SCENES` list controls order and how long each scene stays up.
* `static/style.css`: `html { font-size }` scales the whole interface for the panel.

## On the Pi (after the hardware arrives)

1. Copy this folder to the Pi, create the venv, install requirements, copy your `.env`.
2. Run it as a service so it starts on boot (`/etc/systemd/system/flight-kiosk.service`):

        [Unit]
        Description=Flight kiosk server
        After=network-online.target
        Wants=network-online.target

        [Service]
        WorkingDirectory=/home/pi/flight-kiosk
        ExecStart=/home/pi/flight-kiosk/.venv/bin/python app.py
        Restart=always
        User=pi

        [Install]
        WantedBy=multi-user.target

   Then `sudo systemctl enable --now flight-kiosk`. Change `pi` to your username.
3. Launch Chromium in kiosk mode on login, pointed at the server:

        chromium-browser --kiosk --noerrdialogs --disable-infobars http://localhost:5000

   (The binary is `chromium` on some Raspberry Pi OS releases.)
