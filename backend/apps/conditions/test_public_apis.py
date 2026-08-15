from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.conditions.models import WaterCondition
from apps.spots.models import WaterSpot
from services.conditions_sync import sync_weather
from services.grid_converter import latlon_to_grid
from services.marine import fetch_tide_schedule, fetch_water_temperature
from services.public_data import PublicDataError, get_json, iter_records, result_code
from services.tourapi import search_spot
from services.water_forecast import upsert_forecast_for_spot
from services.weather import fetch_ultra_short_observation


def _kma_items(*pairs):
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": {"items": {"item": [{"category": key, "obsrValue": value} for key, value in pairs]}},
        }
    }


class GridConverterTests(TestCase):
    def test_seoul_city_hall(self):
        self.assertEqual(latlon_to_grid(37.5665, 126.9780), (60, 127))

    def test_haeundae_busan_grid(self):
        nx, ny = latlon_to_grid(35.1586, 129.1603)
        self.assertGreaterEqual(nx, 96)
        self.assertLessEqual(nx, 99)
        self.assertGreaterEqual(ny, 73)
        self.assertLessEqual(ny, 76)


class PublicDataParseTests(TestCase):
    def test_kma_and_khoa_envelopes(self):
        kma = _kma_items(("T1H", "28"))
        self.assertEqual(result_code(kma), "00")
        self.assertEqual(iter_records(kma)[0]["category"], "T1H")

        khoa = {"result": {"data": [{"waterTemp": "24.1"}]}}
        self.assertEqual(iter_records(khoa)[0]["waterTemp"], "24.1")

        live_khoa = {
            "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
            "body": {"items": {"item": [{"wtem": 27.6, "obsrvnDt": "2026-08-15 00:00:00"}]}},
        }
        self.assertEqual(result_code(live_khoa), "00")
        self.assertEqual(iter_records(live_khoa)[0]["wtem"], 27.6)

    def test_tourapi_success_code_0000(self):
        payload = {
            "response": {
                "header": {"resultCode": "0000", "resultMsg": "OK"},
                "body": {"items": {"item": {"contentid": "1"}}},
            }
        }
        self.assertEqual(result_code(payload), "0000")
        with patch("services.public_data.requests.get") as mocked:
            mocked.return_value.status_code = 200
            mocked.return_value.ok = True
            mocked.return_value.json.return_value = payload
            data = get_json("https://example.test", {}, service_key="abc")
        self.assertEqual(iter_records(data)[0]["contentid"], "1")

    def test_unregistered_key_envelope(self):
        payload = {
            "OpenAPI_ServiceResponse": {
                "cmmMsgHeader": {
                    "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
                    "returnAuthMsg": "등록되지 않은 서비스키",
                    "returnReasonCode": "30",
                }
            }
        }
        self.assertEqual(result_code(payload), "30")
        with patch("services.public_data.requests.get") as mocked:
            mocked.return_value.status_code = 403
            mocked.return_value.ok = False
            mocked.return_value.json.return_value = payload
            mocked.return_value.text = "forbidden"
            with self.assertRaises(PublicDataError) as raised:
                get_json("https://example.test", {}, service_key="abc")
        self.assertIn("30", str(raised.exception))
        self.assertIn("활용신청", str(raised.exception))


class WeatherMarineTourParseTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("services.weather._service_key", return_value="test-key")
    @patch("services.weather.get_json")
    def test_ultra_short_maps_categories(self, mocked, _key):
        mocked.return_value = _kma_items(("T1H", "28.4"), ("WSD", "3.2"), ("RN1", "1.5"))
        obs = fetch_ultra_short_observation(35.1586, 129.1603)
        self.assertEqual(obs["air_temp"], 28.4)
        self.assertEqual(obs["wind_speed"], 3.2)
        self.assertEqual(obs["rainfall_recent"], 1.5)

    @patch("services.marine._service_key", return_value="test-key")
    @patch("services.marine.get_json")
    def test_water_temp_and_tide(self, mocked, _key):
        mocked.return_value = {"result": {"data": [{"waterTemp": "24.8"}]}}
        self.assertEqual(fetch_water_temperature("DT_0005"), 24.8)

        mocked.return_value = {
            "result": {
                "data": [
                    {"hlCode": "고조", "tphTime": "2026-08-15 12:05"},
                    {"hlCode": "저조", "tphTime": "18:10"},
                ]
            }
        }
        tide = fetch_tide_schedule("DT_0005")
        self.assertEqual(tide["high_tide"], ["12:05"])
        self.assertEqual(tide["low_tide"], ["18:10"])

        mocked.return_value = {
            "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
            "body": {
                "items": {
                    "item": [
                        {"wtem": 27.6, "obsrvnDt": "2026-08-15 12:00:00"},
                    ]
                }
            },
        }
        self.assertEqual(fetch_water_temperature("DT_0005"), 27.6)

        mocked.return_value = {
            "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
            "body": {
                "items": {
                    "item": [
                        {"predcDt": "2026-08-15 03:35", "extrSe": "2"},
                        {"predcDt": "2026-08-15 10:05", "extrSe": "1"},
                        {"predcDt": "2026-08-15 15:53", "extrSe": "4"},
                        {"predcDt": "2026-08-15 22:15", "extrSe": "3"},
                    ]
                }
            },
        }
        live_tide = fetch_tide_schedule("DT_0005")
        self.assertEqual(live_tide["low_tide"], ["03:35", "15:53"])
        self.assertEqual(live_tide["high_tide"], ["10:05", "22:15"])

    @patch("services.tourapi._service_key", return_value="test-key")
    @patch("services.tourapi.get_json")
    def test_search_spot_uses_first_image(self, mocked, _key):
        mocked.side_effect = [
            {
                "response": {
                    "header": {"resultCode": "0000"},
                    "body": {
                        "items": {
                            "item": {
                                "contentid": "126081",
                                "contenttypeid": "12",
                                "title": "해운대해수욕장",
                                "firstimage": "http://example.com/haeundae.jpg",
                            }
                        }
                    },
                }
            },
            {
                "response": {
                    "header": {"resultCode": "0000"},
                    "body": {"items": {"item": {"overview": "부산의 대표 해수욕장", "firstimage": "http://example.com/haeundae.jpg"}}},
                }
            },
        ]
        data = search_spot("해운대 해수욕장")
        self.assertEqual(data["tourapi_id"], "126081")
        self.assertEqual(data["image_url"], "http://example.com/haeundae.jpg")
        self.assertIn("해수욕장", data["description"])


class ForecastFromOutlookTests(TestCase):
    def setUp(self):
        cache.clear()
        self.spot = WaterSpot.objects.create(
            type="sea",
            name="해운대 해수욕장",
            lat=35.1586,
            lng=129.1603,
            region="부산",
            address="부산",
            kma_mid_reg_id="11H20000",
            khoa_obs_code="DT_0005",
        )
        WaterCondition.objects.create(
            spot=self.spot,
            water_temp=25.0,
            air_temp=28.0,
            wind_speed=2.0,
            wave_height=0.4,
            water_quality_grade="1",
            rainfall_recent=0,
            rip_current_risk="low",
            uv_index=6,
        )

    def test_outlook_changes_daily_index(self):
        today = timezone.localdate()
        outlook = [
            {
                "forecast_date": today + timedelta(days=1),
                "air_temp": 30.0,
                "rainfall_recent": 0,
                "wind_speed": 2.0,
                "wave_height": 0.3,
                "source": "kma",
            },
            {
                "forecast_date": today + timedelta(days=2),
                "air_temp": 18.0,
                "rainfall_recent": 40,
                "wind_speed": 8.0,
                "wave_height": 1.8,
                "source": "kma",
            },
        ]
        rows = upsert_forecast_for_spot(self.spot, outlook=outlook)
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0].predicted_factors["source"], "kma")
        self.assertNotEqual(rows[0].predicted_index, rows[1].predicted_index)

    def test_stored_fallback_without_outlook(self):
        rows = upsert_forecast_for_spot(self.spot, outlook=[])
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0].predicted_factors["source"], "stored")

    @patch("services.conditions_sync.seven_day_outlook")
    @patch("services.conditions_sync.fetch_ultra_short_observation")
    def test_sync_weather_updates_temperature(self, observation, outlook):
        observation.return_value = {"air_temp": 21.0, "wind_speed": 1.2, "rainfall_recent": 0}
        outlook.return_value = []
        sync_weather(self.spot)
        latest = WaterCondition.objects.filter(spot=self.spot).order_by("-fetched_at").first()
        self.assertEqual(latest.air_temp, 21.0)
        self.assertEqual(latest.wind_speed, 1.2)

    def test_missing_key_is_explicit(self):
        with patch("services.public_data.resolve_service_key", return_value=""):
            with self.assertRaises(PublicDataError):
                fetch_ultra_short_observation(35.15, 129.16)
