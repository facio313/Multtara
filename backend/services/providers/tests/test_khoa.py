from __future__ import annotations

import unittest
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import requests

from services.providers.base import (
    ProviderPayloadError,
    ProviderResponseError,
    ProviderTransportError,
)
from services.providers.khoa import (
    BeachForecast,
    KhoaClient,
    MudflatForecast,
    RipCurrentForecast,
    SurfForecast,
)


SECRET = "server-only-khoa-secret"


class FakeResponse:
    def __init__(
        self,
        payload: Any,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        http_error_message: str = "HTTP failure",
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.http_error_message = http_error_message
        self.raise_calls = 0

    def raise_for_status(self) -> None:
        self.raise_calls += 1
        if self.status_code >= 400:
            raise requests.HTTPError(self.http_error_message)

    def json(self) -> Any:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, *outcomes: FakeResponse | Exception) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if not self.outcomes:
            raise AssertionError("unexpected HTTP request")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def payload(
    items: Any,
    *,
    total: Any,
    page_no: Any = 1,
    num_rows: Any = 300,
    code: Any = "00",
    message: str = "NORMAL SERVICE",
    wrapped: bool = True,
) -> dict[str, Any]:
    envelope = {
        "header": {"resultCode": code, "resultMsg": message},
        "body": {
            "totalCount": total,
            "pageNo": page_no,
            "numOfRows": num_rows,
            "items": items,
        },
    }
    return {"response": envelope} if wrapped else envelope


class KhoaClientTests(unittest.TestCase):
    def test_four_official_endpoints_and_typed_fields(self) -> None:
        responses = (
            FakeResponse(
                payload(
                    {
                        "item": [
                            {
                                "bbchNm": "경포해수욕장",
                                "lat": "37.8",
                                "lot": 128.9,
                                "predcYmd": "20260815",
                                "predcNoonSeCd": "오후",
                                "lastScr": "86.5",
                                "totalIndex": "매우좋음",
                                "maxWvhgt": "0.8",
                                "avgWtem": "24.2",
                                "avgArtmp": "28.1",
                                "maxWspd": "4.4",
                            }
                        ]
                    },
                    total="1",
                )
            ),
            FakeResponse(
                payload(
                    {
                        "item": [
                            {
                                "surfPlcNm": "죽도",
                                "predcYmd": "20260815",
                                "lastScr": 71,
                                "totalIndex": "좋음",
                                "grdCn": "초중급자에게 적합",
                                "avgWvhgt": "1.2",
                                "avgWvpd": "8",
                            }
                        ]
                    },
                    total=1,
                    wrapped=False,
                )
            ),
            FakeResponse(
                payload(
                    {
                        "item": [
                            {
                                "mdftExpcnVlgNm": "장화리 갯벌",
                                "predcYmd": "2026-08-15",
                                "mdftExprnBgngTm": "09:10",
                                "mdftExprnEndTm": "11:40",
                                "weather": "맑음",
                                "lastScr": "77",
                                "totalIndex": "좋음",
                            }
                        ]
                    },
                    total=1,
                )
            ),
            FakeResponse(
                payload(
                    {
                        "item": [
                            {
                                "obsvtrId": "GYEONGPO",
                                "obsvtrNm": "경포해수욕장",
                                "obsrvnDt": "20260815143000",
                                "lastScr": "62.5",
                                "lastScrCn": "주의",
                                "wvhgt": "0.7",
                                "wvpd": "7.1",
                                "wtem": "24.3",
                                "artmp": "29.0",
                                "wndrct": "NE",
                                "wspd": "3.2",
                            }
                        ]
                    },
                    total=1,
                )
            ),
        )
        session = FakeSession(*responses)
        client = KhoaClient(SECRET, session=session, timeout=(2.0, 7.0))

        beach = client.fetch_beach_forecasts(
            request_date=date(2026, 8, 15), place_code="HS2"
        )
        surf = client.fetch_surf_forecasts(place_code="SR1")
        mudflat = client.fetch_mudflat_forecasts(place_code="TL31")
        rip = client.fetch_rip_current_forecasts(beach_code="GYEONGPO")

        self.assertIsInstance(beach.records[0], BeachForecast)
        self.assertIsInstance(surf.records[0], SurfForecast)
        self.assertIsInstance(mudflat.records[0], MudflatForecast)
        self.assertIsInstance(rip.records[0], RipCurrentForecast)
        self.assertEqual(beach.records[0].official_grade, "매우좋음")
        self.assertEqual(beach.records[0].score, Decimal("86.5"))
        self.assertEqual(beach.records[0].forecast_date, date(2026, 8, 15))
        self.assertEqual(surf.records[0].official_grade, "좋음")
        self.assertEqual(mudflat.records[0].experience_start_time, "09:10")
        self.assertEqual(rip.records[0].official_index, "62.5")
        self.assertEqual(rip.records[0].observed_at, datetime(2026, 8, 15, 14, 30))

        expected_endpoints = (
            KhoaClient.BEACH_ENDPOINT,
            KhoaClient.SURF_ENDPOINT,
            KhoaClient.MUDFLAT_ENDPOINT,
            KhoaClient.RIP_CURRENT_ENDPOINT,
        )
        self.assertEqual(
            tuple(call["url"] for call in session.calls),
            tuple(f"https://apis.data.go.kr{path}" for path in expected_endpoints),
        )
        self.assertTrue(all(call["timeout"] == (2.0, 7.0) for call in session.calls))
        self.assertEqual(session.calls[0]["params"]["reqDate"], "20260815")
        self.assertEqual(session.calls[0]["params"]["placeCode"], "HS2")
        self.assertEqual(session.calls[3]["params"]["beachCode"], "GYEONGPO")

    def test_paginates_until_reported_total(self) -> None:
        first = FakeResponse(
            payload(
                {"item": {"bbchNm": "첫 번째", "totalIndex": "보통"}},
                total="2",
                page_no="1",
                num_rows="1",
            )
        )
        second = FakeResponse(
            payload(
                {"item": [{"bbchNm": "두 번째", "totalIndex": "좋음"}]},
                total=2,
                page_no=2,
                num_rows=1,
            )
        )
        session = FakeSession(first, second)
        result = KhoaClient(SECRET, session=session, page_size=1).fetch_beach_forecasts()

        self.assertEqual([item.place_name for item in result.records], ["첫 번째", "두 번째"])
        self.assertEqual(result.reported_total_count, 2)
        self.assertEqual([call["params"]["pageNo"] for call in session.calls], [1, 2])

    def test_normalizes_empty_and_single_item_shapes(self) -> None:
        session = FakeSession(
            FakeResponse(payload("", total=0)),
            FakeResponse(
                payload(
                    {"item": {"surfPlcNm": "단일 지점", "totalIndex": "보통"}},
                    total=1,
                )
            ),
        )
        client = KhoaClient(SECRET, session=session)

        empty = client.fetch_mudflat_forecasts()
        single = client.fetch_surf_forecasts()

        self.assertEqual(empty.records, ())
        self.assertEqual(len(single.records), 1)
        self.assertEqual(single.records[0].place_name, "단일 지점")

    def test_rejects_non_success_result_without_exposing_message(self) -> None:
        response = FakeResponse(
            payload(
                "",
                total=0,
                code="30",
                message=f"invalid serviceKey={SECRET}",
            )
        )
        client = KhoaClient(SECRET, session=FakeSession(response))

        with self.assertRaises(ProviderResponseError) as raised:
            client.fetch_beach_forecasts()

        self.assertEqual(raised.exception.result_code, "30")
        self.assertNotIn(SECRET, str(raised.exception))
        self.assertNotIn(SECRET, repr(raised.exception))

    def test_malformed_dates_and_numbers_become_unknown(self) -> None:
        response = FakeResponse(
            payload(
                {
                    "item": {
                        "bbchNm": "형식 오류 지점",
                        "lat": "NaN",
                        "lot": "not-a-number",
                        "predcYmd": "2026-99-99",
                        "lastScr": "점수없음",
                        "totalIndex": "매우좋음",
                        "maxWvhgt": "-",
                    }
                },
                total="not-an-integer",
                num_rows=300,
            )
        )
        result = KhoaClient(SECRET, session=FakeSession(response)).fetch_beach_forecasts()
        record = result.records[0]

        self.assertIsNone(record.latitude)
        self.assertIsNone(record.longitude)
        self.assertIsNone(record.forecast_date)
        self.assertIsNone(record.score)
        self.assertIsNone(record.maximum_wave_height)
        self.assertEqual(record.official_grade, "매우좋음")
        self.assertIsNone(result.reported_total_count)

    def test_retries_429_then_returns_success(self) -> None:
        throttled = FakeResponse(
            {}, status_code=429, headers={"Retry-After": "0"}
        )
        success = FakeResponse(payload("", total=0))
        session = FakeSession(throttled, success)
        delays: list[float] = []

        result = KhoaClient(
            SECRET,
            session=session,
            max_retries=2,
            sleeper=delays.append,
        ).fetch_beach_forecasts()

        self.assertEqual(result.records, ())
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(throttled.raise_calls, 1)
        self.assertEqual(delays, [0.0])

    def test_retries_the_entire_5xx_status_class(self) -> None:
        for status_code in (500, 501, 599):
            with self.subTest(status_code=status_code):
                server_error = FakeResponse({}, status_code=status_code)
                session = FakeSession(
                    server_error,
                    FakeResponse(payload("", total=0)),
                )
                result = KhoaClient(
                    SECRET,
                    session=session,
                    max_retries=1,
                    sleeper=lambda _: None,
                ).fetch_beach_forecasts()

                self.assertEqual(result.records, ())
                self.assertEqual(len(session.calls), 2)
                self.assertEqual(server_error.raise_calls, 1)

    def test_network_and_server_failures_are_bounded_and_sanitized(self) -> None:
        network_session = FakeSession(
            *(
                requests.ConnectionError(f"URL serviceKey={SECRET}")
                for _ in range(3)
            )
        )
        network_client = KhoaClient(
            SECRET,
            session=network_session,
            sleeper=lambda _: None,
        )
        with self.assertRaises(ProviderTransportError) as network_error:
            network_client.fetch_beach_forecasts()
        self.assertEqual(len(network_session.calls), 3)
        self.assertNotIn(SECRET, str(network_error.exception))
        self.assertIsNone(network_error.exception.__context__)

        failures = tuple(
            FakeResponse(
                {},
                status_code=503,
                http_error_message=f"prepared URL serviceKey={SECRET}",
            )
            for _ in range(3)
        )
        server_session = FakeSession(*failures)
        with self.assertRaises(ProviderTransportError) as server_error:
            KhoaClient(
                SECRET,
                session=server_session,
                max_retries=2,
                sleeper=lambda _: None,
            ).fetch_beach_forecasts()

        self.assertEqual(len(server_session.calls), 3)
        self.assertTrue(all(response.raise_calls == 1 for response in failures))
        self.assertEqual(server_error.exception.status_code, 503)
        self.assertNotIn(SECRET, str(server_error.exception))
        self.assertNotIn(SECRET, repr(server_error.exception))
        self.assertIsNone(server_error.exception.__context__)

    def test_invalid_json_and_item_shape_fail_closed(self) -> None:
        invalid_json = KhoaClient(
            SECRET, session=FakeSession(FakeResponse(ValueError(f"bad {SECRET}")))
        )
        with self.assertRaises(ProviderPayloadError) as json_error:
            invalid_json.fetch_beach_forecasts()
        self.assertNotIn(SECRET, str(json_error.exception))
        self.assertIsNone(json_error.exception.__context__)

        invalid_items = KhoaClient(
            SECRET,
            session=FakeSession(FakeResponse(payload({"item": ["bad"]}, total=1))),
        )
        with self.assertRaises(ProviderPayloadError):
            invalid_items.fetch_beach_forecasts()

    def test_secret_and_unknown_raw_fields_never_leave_boundary(self) -> None:
        response = FakeResponse(
            payload(
                {
                    "item": {
                        "bbchNm": "안전한 결과",
                        "totalIndex": "좋음",
                        "serviceKey": SECRET,
                        "unknownRaw": {"credential": SECRET},
                    }
                },
                total=1,
            )
        )
        client = KhoaClient(SECRET, session=FakeSession(response))
        result = client.fetch_beach_forecasts()

        self.assertNotIn(SECRET, repr(client))
        self.assertNotIn(SECRET, repr(result))
        self.assertNotIn(SECRET, repr(asdict(result.records[0])))
        self.assertNotIn("unknownRaw", asdict(result.records[0]))


if __name__ == "__main__":
    unittest.main()
