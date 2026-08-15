from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase

from services.livecam import embed_url, is_live_stream, livecam_payload
from services.safety_radar import assess_safety
from services.tide_timer import next_tide

KST = ZoneInfo("Asia/Seoul")


class TideTimerTests(TestCase):
    def test_next_tide_picks_upcoming_low(self):
        now = datetime(2026, 8, 15, 14, 0, tzinfo=KST)
        nxt = next_tide(
            {"low_tide": ["03:35", "15:53"], "high_tide": ["10:05", "22:15"]},
            now=now,
        )
        self.assertEqual(nxt["kind"], "low")
        self.assertEqual(nxt["time"], "15:53")
        self.assertEqual(nxt["minutes"], 113)
        self.assertTrue(nxt["mudflat_window"])

    def test_wraps_to_tomorrow_when_all_passed(self):
        now = datetime(2026, 8, 15, 23, 0, tzinfo=KST)
        nxt = next_tide({"low_tide": ["03:35"], "high_tide": ["10:05"]}, now=now)
        self.assertEqual(nxt["time"], "03:35")
        self.assertTrue(nxt["is_tomorrow"])


class SafetyRadarTests(TestCase):
    def test_valley_heavy_rain_is_danger(self):
        result = assess_safety("valley", {"rainfall_recent": 42})
        self.assertEqual(result["level"], "danger")
        self.assertTrue(any("강수" in reason for reason in result["reasons"]))

    def test_sea_high_rip_is_danger(self):
        result = assess_safety("sea", {"rip_current_risk": "high", "wave_height": 0.4})
        self.assertEqual(result["level"], "danger")

    def test_sea_korean_caution_rip(self):
        result = assess_safety("sea", {"rip_current_risk": "주의", "wave_height": 0.4})
        self.assertEqual(result["level"], "caution")

    def test_calm_sea_is_safe(self):
        result = assess_safety("sea", {"rip_current_risk": "low", "wave_height": 0.4})
        self.assertEqual(result["level"], "safe")


class LivecamTests(TestCase):
    def test_picsum_is_preview_not_live(self):
        payload = livecam_payload("https://picsum.photos/seed/haeundae/800/450")
        self.assertFalse(payload["is_live"])
        self.assertEqual(payload["embed_url"], "")

    def test_youtube_becomes_embed(self):
        self.assertTrue(is_live_stream("https://www.youtube.com/watch?v=abc123xyz"))
        self.assertEqual(
            embed_url("https://www.youtube.com/watch?v=abc123xyz"),
            "https://www.youtube.com/embed/abc123xyz?autoplay=1&mute=1",
        )
