from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.conditions.models import WaterCondition
from apps.spots.models import WaterSpot
from services.conditions_sync import sync_marine, sync_quality, sync_weather
from services.grid_converter import latlon_to_grid
from services.marine import (
    fetch_marine_extras,
    fetch_rip_current,
    fetch_tide_schedule,
    fetch_water_temperature,
    normalize_rip_level,
)
from services.public_data import PublicDataError, get_json, iter_records, result_code
from services.tourapi import search_spot
from services.water_forecast import upsert_forecast_for_spot
from services.water_quality import fetch_water_quality, grade_from_bod, grade_from_row
from services.weather import fetch_ultra_short_observation, fetch_uv_index, uv_from_row


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

    def test_nier_operation_envelope(self):
        payload = {
            "getWaterMeasuringList": {
                "header": {"code": "00", "message": "NORMAL SERVICE"},
                "item": [{"ITEM_BOD": "3.2", "WMCYMD": "2026.07.01"}],
            }
        }
        self.assertEqual(result_code(payload), "00")
        self.assertEqual(iter_records(payload)[0]["ITEM_BOD"], "3.2")

    def test_application_error_mentions_registration(self):
        payload = {
            "response": {
                "header": {"resultCode": "01", "resultMsg": "APPLICATION_ERROR"},
            }
        }
        with patch("services.public_data.requests.get") as mocked:
            mocked.return_value.status_code = 200
            mocked.return_value.ok = True
            mocked.return_value.json.return_value = payload
            with self.assertRaises(PublicDataError) as raised:
                get_json("https://example.test", {}, service_key="abc")
        self.assertIn("01", str(raised.exception))
        self.assertIn("APPLICATION_ERROR", str(raised.exception))
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

    def test_rip_level_from_korean_grade(self):
        self.assertEqual(normalize_rip_level("관심"), "low")
        self.assertEqual(normalize_rip_level("주의"), "medium")
        self.assertEqual(normalize_rip_level("위험"), "high")

    @patch("services.marine._service_key", return_value="test-key")
    @patch("services.marine.get_json")
    def test_rip_and_beach_index(self, mocked, _key):
        mocked.return_value = {
            "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
            "body": {
                "items": {
                    "item": [
                        {
                            "obsvtrNm": "대천 해수욕장",
                            "lastScrCn": "관심",
                            "lastScr": 7.0,
                            "wvhgt": 0.6,
                            "wtem": 24.2,
                        },
                    ]
                }
            },
        }
        rip = fetch_rip_current("DAECHON")
        self.assertEqual(rip["level"], "low")
        self.assertEqual(rip["wave_height"], 0.6)

        mocked.return_value = {
            "header": {"resultCode": "00"},
            "body": {
                "items": {
                    "item": [
                        {
                            "bbchNm": "광안리해수욕장",
                            "totalIndex": "보통",
                            "maxWvhgt": "0.4",
                            "predcYmd": "2026-08-15",
                            "predcNoonSeCd": "오전",
                        },
                        {
                            "bbchNm": "해운대해수욕장",
                            "totalIndex": "매우좋음",
                            "maxWvhgt": "0.8",
                            "avgWtem": "26.1",
                            "predcYmd": "2026-08-15",
                            "predcNoonSeCd": "오후",
                        },
                        {
                            "bbchNm": "송정솔바람해수욕장",
                            "totalIndex": "좋음",
                            "maxWvhgt": "1.2",
                            "predcYmd": "2026-08-15",
                            "predcNoonSeCd": "오후",
                        },
                    ]
                }
            },
        }
        spot = type("Spot", (), {"name": "해운대 해수욕장", "type": "sea"})()
        extras = fetch_marine_extras(spot)
        self.assertEqual(extras["wave_height"], 0.8)
        self.assertEqual(extras["marine_indices"]["beach"]["grade"], "매우좋음")
        from services.stations import match_score
        self.assertGreaterEqual(match_score("송정 해수욕장", "송정해수욕장"), 90)
        self.assertLess(match_score("송정 해수욕장", "송정솔바람해수욕장"), 90)

    @patch("services.marine._service_key", return_value="test-key")
    @patch("services.marine.get_json")
    def test_unregistered_index_is_skipped(self, mocked, _key):
        mocked.side_effect = PublicDataError("API error 30 for x: 등록되지 않은 서비스키", code="30")
        spot = type("Spot", (), {"name": "해운대 해수욕장", "type": "sea"})()
        self.assertEqual(fetch_marine_extras(spot), {})

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

    @patch("services.weather._service_key", return_value="test-key")
    @patch("services.weather.get_json")
    def test_uv_index_reads_today_or_hourly(self, mocked, _key):
        mocked.return_value = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {"items": {"item": {"today": "8", "h0": "3"}}},
            }
        }
        self.assertEqual(fetch_uv_index("2600000000"), 8.0)
        self.assertEqual(uv_from_row({"h12": "7", "h6": "9"}), 9.0)

    @patch("services.water_quality._service_key", return_value="test-key")
    @patch("services.water_quality.get_json")
    def test_water_quality_grade_from_bod(self, mocked, _key):
        self.assertEqual(grade_from_bod(1.2), "1")
        self.assertEqual(grade_from_bod(4.0), "2")
        self.assertEqual(grade_from_row({"itemBod": "9.5"}), "4")
        self.assertEqual(grade_from_row({"ITEM_BOD": "         0.9"}), "1")
        mocked.return_value = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": {
                        "item": [
                            {"PT_NO": "1001A75", "WMCYMD": "2025.01.01", "ITEM_BOD": "9.5"},
                            {"PT_NO": "1001A75", "WMCYMD": "2026.06.29", "ITEM_BOD": "         3.2"},
                        ]
                    }
                },
            }
        }
        data = fetch_water_quality("1001A75")
        self.assertEqual(data["water_quality_grade"], "2")
        self.assertEqual(data["bod"], 3.2)


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

    @patch("services.conditions_sync.fetch_uv_index", return_value=7.0)
    @patch("services.conditions_sync.seven_day_outlook")
    @patch("services.conditions_sync.fetch_ultra_short_observation")
    def test_sync_weather_updates_temperature(self, observation, outlook, uv):
        observation.return_value = {"air_temp": 21.0, "wind_speed": 1.2, "rainfall_recent": 0}
        outlook.return_value = []
        sync_weather(self.spot)
        latest = WaterCondition.objects.filter(spot=self.spot).order_by("-fetched_at").first()
        self.assertEqual(latest.air_temp, 21.0)
        self.assertEqual(latest.wind_speed, 1.2)
        self.assertEqual(latest.uv_index, 7.0)

    @patch("services.conditions_sync.fetch_water_quality")
    def test_sync_quality_writes_grade(self, mocked):
        inland = WaterSpot.objects.create(
            type="riverside",
            name="동강 래프팅",
            lat=37.283,
            lng=128.655,
            region="강원",
            address="영월",
        )
        WaterCondition.objects.create(spot=inland, water_quality_grade="1")
        mocked.return_value = {"water_quality_grade": "2", "bod": 3.1, "pt_no": "1003A05"}
        result = sync_quality(inland)
        self.assertIn("water_quality_grade", result["changed"])
        latest = WaterCondition.objects.filter(spot=inland).order_by("-fetched_at").first()
        self.assertEqual(latest.water_quality_grade, "2")

    @patch("services.conditions_sync.fetch_marine_extras", return_value={})
    @patch("services.conditions_sync.fetch_tide_schedule")
    @patch("services.conditions_sync.fetch_water_temperature")
    def test_marine_keeps_tide_when_temp_fails(self, temp, tide, _extras):
        temp.side_effect = PublicDataError("API error 41")
        tide.return_value = {"low_tide": ["03:35"], "high_tide": ["10:05"]}
        result = sync_marine(self.spot)
        self.assertIn("tide_schedule", result["changed"])
        latest = WaterCondition.objects.filter(spot=self.spot).order_by("-fetched_at").first()
        self.assertEqual(latest.tide_schedule["low_tide"], ["03:35"])

    @patch("services.conditions_sync.fetch_marine_extras")
    @patch("services.conditions_sync.fetch_tide_schedule")
    @patch("services.conditions_sync.fetch_water_temperature")
    def test_marine_writes_wave_and_rip(self, temp, tide, extras):
        temp.return_value = 24.0
        tide.return_value = {"low_tide": ["03:35"], "high_tide": ["10:05"]}
        extras.return_value = {
            "wave_height": 0.9,
            "rip_current_risk": "low",
            "marine_indices": {"beach": {"kind": "beach", "grade": "좋음"}},
        }
        result = sync_marine(self.spot)
        self.assertIn("wave_height", result["changed"])
        self.assertIn("rip_current_risk", result["changed"])
        latest = WaterCondition.objects.filter(spot=self.spot).order_by("-fetched_at").first()
        self.assertEqual(latest.wave_height, 0.9)
        self.assertEqual(latest.rip_current_risk, "low")
        self.assertEqual(latest.marine_indices["beach"]["grade"], "좋음")

    def test_missing_key_is_explicit(self):
        with patch("services.public_data.resolve_service_key", return_value=""):
            with self.assertRaises(PublicDataError):
                fetch_ultra_short_observation(35.15, 129.16)
