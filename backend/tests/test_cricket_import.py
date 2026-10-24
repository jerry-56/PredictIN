import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cricket_import import market_from_match


class MarketFromMatchTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
        self.match = {
            "id": "provider-match-1",
            "teams": ["India", "Australia"],
            "dateTimeGMT": (self.now + timedelta(hours=2)).replace(tzinfo=None).isoformat(),
            "matchStarted": False,
            "matchEnded": False,
        }

    def test_upcoming_match_becomes_market(self):
        market = market_from_match(self.match, self.now)
        self.assertEqual(market["cricapi_match_id"], "provider-match-1")
        self.assertEqual(market["title"], "Will India win against Australia?")
        self.assertEqual(market["end_date"], "2026-10-23T14:00:00+00:00")

    def test_started_and_imminent_matches_are_skipped(self):
        self.match["matchStarted"] = True
        self.assertIsNone(market_from_match(self.match, self.now))
        self.match["matchStarted"] = False
        self.match["dateTimeGMT"] = (self.now + timedelta(minutes=15)).isoformat()
        self.assertIsNone(market_from_match(self.match, self.now))

    def test_missing_teams_or_start_are_skipped(self):
        self.match["teams"] = ["India"]
        self.assertIsNone(market_from_match(self.match, self.now))
        self.match["teams"] = ["India", "Australia"]
        self.match["dateTimeGMT"] = "TBC"
        self.assertIsNone(market_from_match(self.match, self.now))


if __name__ == "__main__":
    unittest.main()
