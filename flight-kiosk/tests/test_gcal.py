"""Smoke tests for the declined-event filter in sources/gcal.py. No network:
requests.get is mocked with an in-memory .ics. Run with:
  python3 -m unittest discover tests
"""
import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from sources import gcal

FAKE_URL = "https://calendar.google.com/calendar/ical/Me%40Example.com/private-abc123secret/basic.ics"


def ics_time(d):
    return d.strftime("%Y%m%dT%H%M%S")


def make_calendar():
    tz = ZoneInfo(config.TIMEZONE)
    base = (dt.datetime.now(tz) + dt.timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)

    def vevent(uid, summary, start, attendees="", extra=""):
        return (
            "BEGIN:VEVENT\r\n"
            f"UID:{uid}\r\n"
            f"SUMMARY:{summary}\r\n"
            f"DTSTART;TZID={config.TIMEZONE}:{ics_time(start)}\r\n"
            f"DTEND;TZID={config.TIMEZONE}:{ics_time(start + dt.timedelta(hours=1))}\r\n"
            f"{extra}{attendees}"
            "END:VEVENT\r\n"
        )

    me = lambda stat: f"ATTENDEE;PARTSTAT={stat};CN=Me:mailto:me@example.com\r\n"
    other = lambda stat: f"ATTENDEE;PARTSTAT={stat};CN=Other:mailto:other@example.com\r\n"
    alias = lambda stat: f"ATTENDEE;PARTSTAT={stat}:MAILTO:Alias@Work.example\r\n"

    second_day = base + dt.timedelta(days=1)
    events = [
        vevent("declined-single", "Declined single", base, me("DECLINED")),
        vevent("declined-list", "Declined in list", base, other("ACCEPTED") + me("DECLINED")),
        vevent("accepted", "Accepted", base, me("ACCEPTED") + other("DECLINED")),
        vevent("tentative", "Tentative", base, me("TENTATIVE")),
        vevent("needs-action", "No response", base, me("NEEDS-ACTION")),
        vevent("no-attendees", "No attendees", base),
        vevent("other-declined", "Someone else declined", base, other("DECLINED")),
        vevent("alias-declined", "Alias declined", base, alias("DECLINED")),
        # Daily recurring event, accepted, with the second instance declined.
        vevent("standup", "Standup", base, me("ACCEPTED"), "RRULE:FREQ=DAILY;COUNT=3\r\n"),
        vevent("standup", "Standup", second_day, me("DECLINED"),
               f"RECURRENCE-ID;TZID={config.TIMEZONE}:{ics_time(second_day)}\r\n"),
    ]
    body = "".join(events)
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\n" + body + "END:VCALENDAR\r\n").encode()


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


class DeclinedFilterTests(unittest.TestCase):
    def setUp(self):
        gcal._cache = {"t": 0.0, "data": None}
        gcal._warned_no_email = False

    def run_events(self, url=FAKE_URL, emails=()):
        with patch.object(config, "ICAL_URL", url), \
             patch.object(config, "CALENDAR_EMAILS", list(emails)), \
             patch("sources.gcal.requests.get", return_value=FakeResponse(make_calendar())):
            data = gcal.get_events()
        self.assertIsNone(data["error"])
        return [e["title"] for e in data["events"]]

    def test_email_parsed_from_url(self):
        with patch.object(config, "ICAL_URL", FAKE_URL), patch.object(config, "CALENDAR_EMAILS", []):
            self.assertEqual(gcal.my_emails(), {"me@example.com"})

    def test_declined_hidden_others_kept(self):
        titles = self.run_events()
        for hidden in ("Declined single", "Declined in list"):
            self.assertNotIn(hidden, titles)
        for kept in ("Accepted", "Tentative", "No response", "No attendees", "Someone else declined"):
            self.assertIn(kept, titles)
        self.assertIn("Alias declined", titles)  # alias not configured yet

    def test_calendar_emails_alias(self):
        titles = self.run_events(emails=["mailto:alias@work.example"])
        self.assertNotIn("Alias declined", titles)

    def test_declined_recurring_instance_only(self):
        titles = self.run_events()
        self.assertEqual(titles.count("Standup"), 2)  # 3 instances, 1 declined

    def test_no_email_shows_everything_and_warns_once(self):
        url = "https://example.com/some/other/feed.ics"
        with self.assertLogs("calendar", level="WARNING") as logs:
            titles = self.run_events(url=url)
            gcal._cache = {"t": 0.0, "data": None}
            self.run_events(url=url)
        self.assertEqual(len(logs.output), 1)
        self.assertNotIn("feed.ics", logs.output[0])
        self.assertIn("Declined single", titles)
        self.assertEqual(titles.count("Standup"), 3)

    def test_error_message_never_contains_url(self):
        import requests
        err = requests.HTTPError(f"404 Client Error: Not Found for url: {FAKE_URL}")
        with patch.object(config, "ICAL_URL", FAKE_URL), \
             patch("sources.gcal.requests.get", side_effect=err), \
             self.assertLogs("calendar", level="ERROR") as logs:
            data = gcal.get_events()
        self.assertNotIn("abc123secret", data["error"])
        self.assertNotIn("abc123secret", "".join(logs.output))


if __name__ == "__main__":
    unittest.main()
