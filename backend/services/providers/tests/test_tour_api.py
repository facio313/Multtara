from __future__ import annotations

import unittest
from dataclasses import asdict
from decimal import Decimal
from typing import Any

import requests

from services.providers.base import ProviderPayloadError, ProviderResponseError
from services.providers.tour_api import TourApiClient


SECRET = "server-only-tour-secret"


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.status_code = 200
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.payload


class FakeSession:
    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def payload(items: Any, *, total: Any, code: str = "0000") -> dict[str, Any]:
    return {
        "response": {
            "header": {"resultCode": code, "resultMsg": f"hidden {SECRET}"},
            "body": {
                "totalCount": total,
                "numOfRows": 100,
                "pageNo": 1,
                "items": {"item": items} if items != "" else "",
            },
        }
    }


class TourApiClientTests(unittest.TestCase):
    def test_nearby_place_is_typed_and_uses_current_v2_endpoint(self) -> None:
        session = FakeSession(
            FakeResponse(
                payload(
                    {
                        "contentid": "126508",
                        "contenttypeid": "12",
                        "title": "경포해변",
                        "addr1": "강원특별자치도 강릉시",
                        "mapx": "128.9075",
                        "mapy": "37.8057",
                        "dist": "1234.5",
                        "firstimage": "http://tong.visitkorea.or.kr/image.jpg",
                        "modifiedtime": "20260815143000",
                    },
                    total=1,
                )
            )
        )
        client = TourApiClient(SECRET, session=session)
        result = client.fetch_nearby(
            latitude=37.8057, longitude=128.9075, radius_m=5000
        )
        record = result.records[0]

        self.assertEqual(record.content_id, "126508")
        self.assertEqual(record.latitude, Decimal("37.8057"))
        self.assertEqual(record.distance_m, Decimal("1234.5"))
        self.assertEqual(record.image_url, "https://tong.visitkorea.or.kr/image.jpg")
        self.assertIsNotNone(record.modified_at)
        self.assertEqual(
            session.calls[0]["url"],
            "https://apis.data.go.kr/B551011/KorService2/locationBasedList2",
        )
        self.assertEqual(session.calls[0]["params"]["MobileOS"], "WEB")
        self.assertEqual(session.calls[0]["params"]["serviceKey"], SECRET)

    def test_language_gateway_and_keyword_are_explicit(self) -> None:
        session = FakeSession(FakeResponse(payload("", total=0)))
        client = TourApiClient(SECRET, language="ja", session=session)
        result = client.search_keyword("海")
        self.assertEqual(result.records, ())
        self.assertEqual(client.language, "ja")
        self.assertIn("/JpnService2/searchKeyword2", session.calls[0]["url"])
        self.assertEqual(session.calls[0]["params"]["keyword"], "海")

    def test_detail_preserves_provider_text_without_raw_fields(self) -> None:
        session = FakeSession(
            FakeResponse(
                payload(
                    {
                        "contentid": "1",
                        "title": "장소",
                        "homepage": "<a href='https://example.test'>공식</a>",
                        "overview": "<p>설명</p>",
                        "serviceKey": SECRET,
                        "unknownRaw": {"secret": SECRET},
                    },
                    total=1,
                )
            )
        )
        client = TourApiClient(SECRET, session=session)
        detail = client.fetch_detail("1").records[0]
        self.assertIn("<p>", detail.overview)
        self.assertNotIn(SECRET, repr(client))
        self.assertNotIn(SECRET, repr(asdict(detail)))
        self.assertNotIn("unknownRaw", asdict(detail))

    def test_missing_identifier_truncated_pagination_and_error_fail_closed(self) -> None:
        missing_id = FakeResponse(payload({"title": "잘못된 항목"}, total=1))
        with self.assertRaises(ProviderPayloadError):
            TourApiClient(SECRET, session=FakeSession(missing_id)).fetch_nearby(
                latitude=37.8, longitude=128.9
            )

        truncated = FakeResponse(payload("", total=2))
        with self.assertRaises(ProviderPayloadError):
            TourApiClient(SECRET, session=FakeSession(truncated)).fetch_nearby(
                latitude=37.8, longitude=128.9
            )

        rejected = FakeResponse(payload("", total=0, code="30"))
        with self.assertRaises(ProviderResponseError) as raised:
            TourApiClient(SECRET, session=FakeSession(rejected)).fetch_nearby(
                latitude=37.8, longitude=128.9
            )
        self.assertNotIn(SECRET, str(raised.exception))

    def test_request_inputs_are_bounded(self) -> None:
        client = TourApiClient(SECRET, session=FakeSession())
        with self.assertRaisesRegex(ValueError, "radius_m"):
            client.fetch_nearby(latitude=37.8, longitude=128.9, radius_m=20_001)
        with self.assertRaisesRegex(ValueError, "latitude"):
            client.fetch_nearby(latitude=91, longitude=128.9)
        with self.assertRaisesRegex(ValueError, "keyword"):
            client.search_keyword(" ")


if __name__ == "__main__":
    unittest.main()
