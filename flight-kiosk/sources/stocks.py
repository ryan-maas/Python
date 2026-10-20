"""Stock quotes from Finnhub (free tier: delayed or real-time US quotes, 60 calls/min)."""
import logging
import time

import requests

import config

log = logging.getLogger("stocks")
_cache = {"t": 0.0, "data": None}

# Finnhub's free tier has no fund-name lookup for ETFs, so the names for the
# symbols this kiosk tracks are kept here. Unknown symbols just show the ticker.
NAMES = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "DIA": "Dow 30",
    "IWM": "Russell 2000",
    "VTI": "Total US Market",
    "VXUS": "Total Intl Market",
    "AGG": "US Aggregate Bond",
    "TLT": "20+ Yr Treasury",
}


def get_quotes():
    if not config.FINNHUB_KEY:
        return {"error": "Add a free Finnhub key as FINNHUB_KEY in .env", "quotes": []}
    if _cache["data"] and time.time() - _cache["t"] < config.STOCKS_TTL:
        return _cache["data"]

    quotes = []
    for sym in config.STOCK_SYMBOLS:
        try:
            r = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": sym, "token": config.FINNHUB_KEY},
                timeout=10,
            )
            r.raise_for_status()
            q = r.json()
            if not q.get("c"):
                continue  # unknown symbol returns zeros
            quotes.append({
                "symbol": sym,
                "name": NAMES.get(sym, ""),
                "price": q["c"],
                "change": q.get("d"),
                "percent": q.get("dp"),
            })
        except Exception as exc:
            log.warning("quote failed for %s: %s", sym, exc)

    if not quotes and _cache["data"]:
        return _cache["data"]
    data = {"error": None if quotes else "No quotes returned", "quotes": quotes}
    _cache.update(t=time.time(), data=data)
    return data
