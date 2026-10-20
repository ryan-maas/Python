"""News headlines: RSS feeds, with Finnhub market news blended into Markets.

Headlines only, no summaries or links. Each feed is fetched and parsed on its
own, so one dead feed cannot hide the others.
"""
import calendar
import logging
import re
import time

import feedparser
import requests

import config

log = logging.getLogger("news")
_cache = {"t": 0.0, "data": None}

USER_AGENT = "Mozilla/5.0 (compatible; flight-kiosk/1.0)"


def _fetch_rss(name, url):
    """Returns (items, ok). ok is False only when the feed itself failed."""
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
        r.raise_for_status()
        parsed = feedparser.parse(r.content)  # parse our own bytes: feedparser's own fetch has no timeout
        items = []
        for e in parsed.entries:
            title = (e.get("title") or "").strip()
            tm = e.get("published_parsed") or e.get("updated_parsed")
            if not title or not tm:
                continue
            items.append({
                "title": title,
                "source": name,
                "published": calendar.timegm(tm),  # struct_time is already UTC
            })
        return items, True
    except Exception as exc:
        log.warning("feed failed for %s: %s", name, exc)
        return [], False


def _fetch_finnhub():
    """Returns (items, ok). ok is None when skipped (no key): neither a
    success nor a failure, so it cannot mask every RSS feed failing."""
    if not config.FINNHUB_KEY:
        return [], None
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/news",
            params={"category": "general", "token": config.FINNHUB_KEY},
            timeout=10,
        )
        r.raise_for_status()
        items = []
        for a in r.json():
            title = (a.get("headline") or "").strip()
            if not title or not a.get("datetime"):
                continue
            items.append({
                "title": title,
                "source": a.get("source") or "Finnhub",
                "published": a["datetime"],
            })
        return items, True
    except Exception as exc:
        log.warning("Finnhub news fetch failed: %s", exc)
        return [], False


def _normalize_title(title):
    return re.sub(r"[^\w\s]", "", title.lower()).strip()


def _finalize(items):
    """Drop stale items, remove near-duplicate titles, sort newest first,
    then cap how many a single source can contribute and the column total.
    If the cap leaves the column short (too few sources), backfill with the
    remaining items newest first, even from sources that hit the cap."""
    cutoff = time.time() - config.NEWS_MAX_AGE_HOURS * 3600
    items = [it for it in items if it["published"] >= cutoff]
    items.sort(key=lambda it: it["published"], reverse=True)

    seen_titles, unique = set(), []
    for it in items:
        key = _normalize_title(it["title"])
        if key in seen_titles:
            continue
        seen_titles.add(key)
        unique.append(it)

    seen_sources, out, extra = {}, [], []
    for it in unique:
        if len(out) >= config.NEWS_MAX_ITEMS:
            break
        if seen_sources.get(it["source"], 0) >= config.NEWS_MAX_PER_SOURCE:
            extra.append(it)
            continue
        seen_sources[it["source"]] = seen_sources.get(it["source"], 0) + 1
        out.append(it)

    if len(out) < config.NEWS_MAX_ITEMS:
        out.extend(extra[:config.NEWS_MAX_ITEMS - len(out)])
        out.sort(key=lambda it: it["published"], reverse=True)
    return out


def get_news():
    if _cache["data"] and time.time() - _cache["t"] < config.NEWS_TTL:
        return _cache["data"]

    general_raw, markets_raw = [], []
    any_ok = False

    for name, url in config.NEWS_GENERAL_FEEDS:
        items, ok = _fetch_rss(name, url)
        general_raw.extend(items)
        any_ok = any_ok or ok

    for name, url in config.NEWS_MARKETS_FEEDS:
        items, ok = _fetch_rss(name, url)
        markets_raw.extend(items)
        any_ok = any_ok or ok

    items, ok = _fetch_finnhub()
    markets_raw.extend(items)
    if ok is not None:
        any_ok = any_ok or ok

    if not any_ok:
        if _cache["data"]:
            return _cache["data"]
        return {"error": "Could not load news", "updated": None, "general": [], "markets": []}

    data = {
        "error": None,
        "updated": time.time(),
        "general": _finalize(general_raw),
        "markets": _finalize(markets_raw),
    }
    _cache.update(t=time.time(), data=data)
    return data
