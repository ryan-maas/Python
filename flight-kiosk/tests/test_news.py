"""Smoke tests for sources/news.py. No network access: requests.get is mocked
and feedparser parses in-memory RSS content. Run with:  python3 -m unittest discover tests
"""
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from sources import news

RSS_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test Feed</title>
{items}
</channel></rss>"""

ITEM_TEMPLATE = "<item><title>{title}</title><pubDate>{pubdate}</pubDate></item>"


def rfc822(dt):
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def make_feed(entries):
    """entries: list of (title, datetime) tuples."""
    items = "\n".join(ITEM_TEMPLATE.format(title=t, pubdate=rfc822(d)) for t, d in entries)
    return RSS_TEMPLATE.format(items=items).encode("utf-8")


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


def patched_get(content=None, exc=None):
    def _get(url, headers=None, timeout=None, params=None):
        if exc:
            raise exc
        return FakeResponse(content)
    return _get


class NewsTests(unittest.TestCase):
    def setUp(self):
        news._cache = {"t": 0.0, "data": None}
        self.now = datetime.now(timezone.utc)

    def test_parses_recent_item(self):
        content = make_feed([("Hello world", self.now)])
        with patch("sources.news.requests.get", patched_get(content)):
            items, ok = news._fetch_rss("NPR", "http://example.invalid/rss")
        self.assertTrue(ok)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Hello world")
        self.assertEqual(items[0]["source"], "NPR")
        self.assertAlmostEqual(items[0]["published"], self.now.timestamp(), delta=2)

    def test_feed_failure_is_isolated(self):
        with patch("sources.news.requests.get", patched_get(exc=ConnectionError("boom"))):
            items, ok = news._fetch_rss("DeadFeed", "http://example.invalid/rss")
        self.assertEqual(items, [])
        self.assertFalse(ok)

    def test_finalize_drops_items_older_than_max_age(self):
        fresh = {"title": "Fresh", "source": "A", "published": time.time()}
        stale = {
            "title": "Stale",
            "source": "A",
            "published": time.time() - (config.NEWS_MAX_AGE_HOURS + 1) * 3600,
        }
        out = news._finalize([fresh, stale])
        self.assertEqual([it["title"] for it in out], ["Fresh"])

    def test_finalize_dedupes_near_identical_titles(self):
        now = time.time()
        a = {"title": "Fed cuts rates!!", "source": "A", "published": now}
        b = {"title": "fed cuts rates", "source": "B", "published": now - 10}
        out = news._finalize([a, b])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["title"], "Fed cuts rates!!")  # first (newest) wins

    def test_finalize_caps_items_per_source_when_enough_sources(self):
        now = time.time()
        items = [
            {"title": f"Prolific {i}", "source": "Prolific", "published": now - i}
            for i in range(config.NEWS_MAX_ITEMS)
        ]
        items += [
            {"title": f"Other {i}", "source": f"Other{i}", "published": now - 1000 - i}
            for i in range(config.NEWS_MAX_ITEMS)
        ]
        out = news._finalize(items)
        self.assertEqual(len(out), config.NEWS_MAX_ITEMS)
        self.assertEqual(sum(it["source"] == "Prolific" for it in out), config.NEWS_MAX_PER_SOURCE)

    def test_finalize_backfills_single_source_to_max_items(self):
        now = time.time()
        items = [
            {"title": f"Story {i}", "source": "Prolific", "published": now - i}
            for i in range(config.NEWS_MAX_PER_SOURCE + 5)
        ]
        out = news._finalize(items)
        self.assertEqual(len(out), min(config.NEWS_MAX_ITEMS, len(items)))
        self.assertEqual([it["title"] for it in out], [f"Story {i}" for i in range(len(out))])

    def test_finalize_backfill_fills_shortfall_newest_first(self):
        now = time.time()
        # Source A: 6 items, B: 1 item. Cap gives A4 + B1 = 5, backfill adds A's next 2 newest
        # (only 7 exist in total), and the result stays sorted newest first.
        items = [{"title": f"A{i}", "source": "A", "published": now - i * 10} for i in range(6)]
        items.append({"title": "B0", "source": "B", "published": now - 25})
        out = news._finalize(items)
        self.assertEqual([it["title"] for it in out], ["A0", "A1", "A2", "B0", "A3", "A4", "A5"])

    def test_finalize_backfill_skips_duplicates(self):
        now = time.time()
        items = [{"title": f"A{i}", "source": "A", "published": now - i} for i in range(6)]
        items.append({"title": "a5!", "source": "A", "published": now - 100})  # dupe of A5
        out = news._finalize(items)
        self.assertEqual(len(out), 6)

    def test_finalize_caps_total_items_across_sources(self):
        now = time.time()
        items = []
        for i in range(config.NEWS_MAX_ITEMS + 10):
            items.append({"title": f"Story {i}", "source": f"Source{i}", "published": now - i})
        out = news._finalize(items)
        self.assertEqual(len(out), config.NEWS_MAX_ITEMS)

    def test_finalize_sorts_newest_first(self):
        now = time.time()
        older = {"title": "Older", "source": "A", "published": now - 3600}
        newer = {"title": "Newer", "source": "A", "published": now}
        out = news._finalize([older, newer])
        self.assertEqual([it["title"] for it in out], ["Newer", "Older"])

    def test_finnhub_skipped_without_key_no_error(self):
        with patch.object(config, "FINNHUB_KEY", ""):
            items, ok = news._fetch_finnhub()
        self.assertEqual(items, [])
        self.assertIsNone(ok)  # skipped, not a failure

    def test_get_news_survives_one_dead_feed(self):
        good_content = make_feed([("Still works", self.now)])

        def fake_get(url, headers=None, timeout=None, params=None):
            if "dead" in url:
                raise ConnectionError("boom")
            return FakeResponse(good_content)

        with patch.object(config, "NEWS_GENERAL_FEEDS", [("Dead", "http://dead.invalid"), ("Good", "http://good.invalid")]), \
             patch.object(config, "NEWS_MARKETS_FEEDS", []), \
             patch.object(config, "FINNHUB_KEY", ""), \
             patch("sources.news.requests.get", fake_get):
            data = news.get_news()

        self.assertIsNone(data["error"])
        self.assertEqual(len(data["general"]), 1)
        self.assertEqual(data["general"][0]["title"], "Still works")

    def test_get_news_falls_back_to_cache_when_everything_fails(self):
        cached = {"error": None, "updated": 1.0, "general": [{"title": "old"}], "markets": []}
        news._cache = {"t": time.time() - 9999, "data": cached}

        with patch.object(config, "NEWS_GENERAL_FEEDS", [("Dead", "http://dead.invalid")]), \
             patch.object(config, "NEWS_MARKETS_FEEDS", [("AlsoDead", "http://dead2.invalid")]), \
             patch.object(config, "FINNHUB_KEY", ""), \
             patch("sources.news.requests.get", patched_get(exc=ConnectionError("boom"))):
            data = news.get_news()

        self.assertEqual(data, cached)

    def test_get_news_returns_error_string_when_no_cache_and_everything_fails(self):
        with patch.object(config, "NEWS_GENERAL_FEEDS", [("Dead", "http://dead.invalid")]), \
             patch.object(config, "NEWS_MARKETS_FEEDS", []), \
             patch.object(config, "FINNHUB_KEY", ""), \
             patch("sources.news.requests.get", patched_get(exc=ConnectionError("boom"))):
            data = news.get_news()

        self.assertIsInstance(data["error"], str)
        self.assertEqual(data["general"], [])
        self.assertEqual(data["markets"], [])


if __name__ == "__main__":
    unittest.main()
