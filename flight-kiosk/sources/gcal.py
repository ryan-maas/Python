"""Google Calendar via the calendar's secret iCal address (no OAuth needed)."""
import datetime as dt
import logging
import time
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

import recurring_ical_events
import requests
from icalendar import Calendar

import config

log = logging.getLogger("calendar")
_cache = {"t": 0.0, "data": None}
_warned_no_email = False


def _clean_email(value):
    s = str(value).strip().lower()
    return s[len("mailto:"):] if s.startswith("mailto:") else s


def _redact(text):
    """requests errors include the URL (and its secret token), so strip it out."""
    url = config.ICAL_URL
    for secret in (url, urlsplit(url).path):
        if secret:
            text = text.replace(secret, "<ICAL_URL>")
    return text


def my_emails():
    """Addresses that count as me: the one in the iCal URL path
    (/calendar/ical/<url-encoded email>/private-.../basic.ics) plus CALENDAR_EMAILS.
    Never log ICAL_URL itself, it contains a secret token."""
    emails = set()
    try:
        parts = urlsplit(config.ICAL_URL).path.split("/")
        if "ical" in parts:
            candidate = _clean_email(unquote(parts[parts.index("ical") + 1]))
            if "@" in candidate:
                emails.add(candidate)
    except (ValueError, IndexError):
        pass
    emails.update(_clean_email(e) for e in config.CALENDAR_EMAILS)
    emails.discard("")
    return emails


def is_declined(component, emails):
    """True if my ATTENDEE entry on this event (or this one instance) says DECLINED."""
    attendees = component.get("ATTENDEE")
    if attendees is None:
        return False
    if not isinstance(attendees, list):
        attendees = [attendees]
    for a in attendees:
        if _clean_email(a) in emails:
            params = getattr(a, "params", {})
            if str(params.get("PARTSTAT", "")).upper() == "DECLINED":
                return True
    return False


def get_events():
    global _warned_no_email
    if not config.ICAL_URL:
        return {"error": "Add your calendar's secret iCal address as ICAL_URL in .env", "events": []}
    if _cache["data"] and time.time() - _cache["t"] < config.CALENDAR_TTL:
        return _cache["data"]

    tz = ZoneInfo(config.TIMEZONE)
    now = dt.datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(days=config.CALENDAR_DAYS)

    emails = my_emails()
    if not emails and not _warned_no_email:
        log.warning("could not determine your calendar email, so declined events are shown; set CALENDAR_EMAILS")
        _warned_no_email = True

    try:
        r = requests.get(config.ICAL_URL, timeout=20)
        r.raise_for_status()
        cal = Calendar.from_ical(r.content)
        events = []
        for ev in recurring_ical_events.of(cal).between(start, end):
            if emails and is_declined(ev, emails):
                continue
            s = ev["DTSTART"].dt
            e = ev["DTEND"].dt if ev.get("DTEND") else s
            all_day = not isinstance(s, dt.datetime)
            if all_day:
                s_dt = dt.datetime.combine(s, dt.time.min, tzinfo=tz)
                e_dt = dt.datetime.combine(e, dt.time.min, tzinfo=tz)
            else:
                s_dt = s.astimezone(tz) if s.tzinfo else s.replace(tzinfo=tz)
                e_dt = e.astimezone(tz) if getattr(e, "tzinfo", None) else e.replace(tzinfo=tz)
                if e_dt < now:
                    continue  # already finished today
            events.append({
                "title": str(ev.get("SUMMARY", "(no title)")),
                "start": s_dt.isoformat(),
                "end": e_dt.isoformat(),
                "all_day": all_day,
                "location": str(ev.get("LOCATION", "")) or None,
            })
        events.sort(key=lambda x: (x["start"], x["title"]))
        data = {"error": None, "events": events}
    except Exception as exc:
        msg = _redact(str(exc))
        log.error("calendar fetch failed: %s", msg)
        if _cache["data"]:
            return _cache["data"]  # show stale data rather than nothing
        return {"error": f"Could not load calendar: {msg}", "events": []}

    _cache.update(t=time.time(), data=data)
    return data
