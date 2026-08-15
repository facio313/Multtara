from __future__ import annotations

import unittest
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import requests

from services.providers.base import ProviderPayloadError, ProviderResponseError
from services.providers.kma import KmaClient, WeatherValue, latlon_to_grid


SECRET = "server-only-kma-secret"
KST = ZoneInfo("Asia/Seoul")
ISSUED_AT = datetime(2026, 8, 16, 5, 0, tzinfo=KST)


class FakeResponse:
    def __init__(self, payload: Any, *, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError("sanitized fake failure")

    def json(self) -> Any:
        return self.payload


class FakeSession:
    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def payload(items: Any, *, total: Any, code: str = "00") -> dict[str, Any]:
    return {
        "response": {
            "header": {"resultCode": code, "resultMsg": f"hidden {SECRET}"},
            "body": {
                "totalCount": total,
                "pageNo": 1,
                "numOfRows": 1000,
                "items": {"item": items} if items != "" else "",
            },
        }
    }


class KmaClientTests(unittest.TestCase):
    def test_official_lambert_grid_conversion_vectors(self) -> None:
        seoul = latlon_to_grid(37.5665, 126.978)
        busan = latlon_to_grid(35.1796, 129.0756)
        gangneung = latlon_to_grid(37.7519, 128.8761)
        self.assertEqual((seoul.x, seoul.y), (60, 127))
        self.assertEqual((busan.x, busan.y), (98, 76))
        self.assertEqual((gangneung.x, gangneung.y), (92, 132))
        with self.assertRaisesRegex(ValueError, "geographic bounds"):
            latlon_to_grid(91, 126)

    def test_nowcast_and_forecast_are_typed_and_timezone_aware(self) -> None:
        nowcast = payload(
            [
                {
                    "baseDate": "20260816",
                    "baseTime": "0500",
                    "category": "T1H",
                    "obsrValue": "24.7",
                    "nx": 92,
                    "ny": 131,
                },
                {
                    "baseDate": "20260816",
                    "baseTime": "0500",
                    "category": "PTY",
                    "obsrValue": "0",
                    "nx": 92,
                    "ny": 131,
                },
            ],
            total=2,
        )
        forecast = payload(
            [
                {
                    "baseDate": "20260816",
                    "baseTime": "0500",
                    "fcstDate": "20260816",
                    "fcstTime": "0800",
                    "category": "WSD",
                    "fcstValue": "3.4",
                    "nx": 92,
                    "ny": 131,
                },
                {
                    "baseDate": "20260816",
                    "baseTime": "0500",
                    "fcstDate": "20260816",
                    "fcstTime": "0800",
                    "category": "PCP",
                    "fcstValue": "강수없음",
                    "nx": 92,
                    "ny": 131,
                },
            ],
            total="2",
        )
        session = FakeSession(FakeResponse(nowcast), FakeResponse(forecast))
        client = KmaClient(SECRET, session=session)

        observed = client.fetch_nowcast(issued_at=ISSUED_AT, grid_x=92, grid_y=131)
        predicted = client.fetch_short_forecast(
            issued_at=ISSUED_AT, grid_x=92, grid_y=131
        )

        self.assertIsInstance(observed.records[0], WeatherValue)
        self.assertEqual(observed.records[0].value, Decimal("24.7"))
        self.assertEqual(observed.records[0].unit, "celsius")
        self.assertEqual(observed.records[1].value, "0")
        self.assertEqual(predicted.records[0].value, Decimal("3.4"))
        self.assertEqual(predicted.records[0].valid_at.hour, 8)
        self.assertEqual(predicted.records[0].valid_at.tzinfo, KST)
        self.assertEqual(predicted.records[1].value, "강수없음")
        self.assertEqual(
            session.calls[0]["url"],
            f"https://apis.data.go.kr{KmaClient.NOWCAST_ENDPOINT}",
        )
        self.assertEqual(session.calls[0]["params"]["base_date"], "20260816")
        self.assertEqual(session.calls[0]["params"]["serviceKey"], SECRET)

    def test_malformed_numeric_value_becomes_unknown_not_zero(self) -> None:
        response = FakeResponse(
            payload(
                {
                    "baseDate": "20260816",
                    "baseTime": "0500",
                    "category": "WSD",
                    "obsrValue": "not-a-number",
                    "nx": 92,
                    "ny": 131,
                },
                total=1,
            )
        )
        record = KmaClient(SECRET, session=FakeSession(response)).fetch_nowcast(
            issued_at=ISSUED_AT, grid_x=92, grid_y=131
        ).records[0]
        self.assertIsNone(record.value)

    def test_missing_forecast_time_and_truncated_page_fail_closed(self) -> None:
        missing_time = FakeResponse(
            payload(
                {"category": "TMP", "fcstValue": "25", "nx": 92, "ny": 131},
                total=1,
            )
        )
        with self.assertRaises(ProviderPayloadError):
            KmaClient(SECRET, session=FakeSession(missing_time)).fetch_short_forecast(
                issued_at=ISSUED_AT, grid_x=92, grid_y=131
            )

        truncated = FakeResponse(payload("", total=2))
        with self.assertRaises(ProviderPayloadError):
            KmaClient(SECRET, session=FakeSession(truncated)).fetch_nowcast(
                issued_at=ISSUED_AT, grid_x=92, grid_y=131
            )

    def test_response_issue_time_and_grid_must_match_request(self) -> None:
        base_item = {
            "baseDate": "20260816",
            "baseTime": "0500",
            "category": "T1H",
            "obsrValue": "24.7",
            "nx": 92,
            "ny": 131,
        }
        mismatches = (
            {**base_item, "baseTime": "0400"},
            {**base_item, "nx": 93},
            {**base_item, "ny": 132},
            {**base_item, "baseTime": None},
        )
        for item in mismatches:
            with self.subTest(item=item):
                response = FakeResponse(payload(item, total=1))
                with self.assertRaises(ProviderPayloadError):
                    KmaClient(SECRET, session=FakeSession(response)).fetch_nowcast(
                        issued_at=ISSUED_AT, grid_x=92, grid_y=131
                    )

    def test_missing_response_issue_and_grid_fields_use_requested_identity(self) -> None:
        response = FakeResponse(
            payload(
                {
                    "category": "T1H",
                    "obsrValue": "24.7",
                },
                total=1,
            )
        )
        record = KmaClient(SECRET, session=FakeSession(response)).fetch_nowcast(
            issued_at=ISSUED_AT, grid_x=92, grid_y=131
        ).records[0]
        self.assertEqual(record.issued_at, ISSUED_AT)
        self.assertEqual((record.grid_x, record.grid_y), (92, 131))

    def test_provider_error_and_unknown_fields_do_not_leak_secret(self) -> None:
        rejected = FakeResponse(payload("", total=0, code="30"))
        with self.assertRaises(ProviderResponseError) as raised:
            KmaClient(SECRET, session=FakeSession(rejected)).fetch_nowcast(
                issued_at=ISSUED_AT, grid_x=92, grid_y=131
            )
        self.assertNotIn(SECRET, str(raised.exception))

        success = FakeResponse(
            payload(
                {
                    "baseDate": "20260816",
                    "baseTime": "0500",
                    "category": "T1H",
                    "obsrValue": "25",
                    "nx": 92,
                    "ny": 131,
                    "serviceKey": SECRET,
                    "unknownRaw": {"secret": SECRET},
                },
                total=1,
            )
        )
        client = KmaClient(SECRET, session=FakeSession(success))
        record = client.fetch_nowcast(
            issued_at=ISSUED_AT, grid_x=92, grid_y=131
        ).records[0]
        self.assertNotIn(SECRET, repr(client))
        self.assertNotIn(SECRET, repr(asdict(record)))
        self.assertNotIn("unknownRaw", asdict(record))

    def test_inputs_are_bounded(self) -> None:
        client = KmaClient(SECRET, session=FakeSession())
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            client.fetch_nowcast(
                issued_at=datetime(2026, 8, 16, 5, 0), grid_x=92, grid_y=131
            )
        with self.assertRaisesRegex(ValueError, "grid_x"):
            client.fetch_nowcast(issued_at=ISSUED_AT, grid_x=0, grid_y=131)


if __name__ == "__main__":
    unittest.main()
