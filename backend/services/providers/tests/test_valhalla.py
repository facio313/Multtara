from __future__ import annotations

from unittest import TestCase

import requests

from services.providers.base import (
    ProviderConfigurationError,
    ProviderPayloadError,
    ProviderTransportError,
)
from services.providers.valhalla import RouteLocation, ValhallaMatrixClient


class FakeResponse:
    def __init__(self, payload, *, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("prepared URL must not escape")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response=None, *, error=False):
        self.response = response
        self.error = error
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise requests.ConnectionError("https://secret.example/path?token=bad")
        return self.response


class ValhallaMatrixClientTests(TestCase):
    locations = (
        RouteLocation(1, 37.8, 128.9),
        RouteLocation(2, 37.81, 128.91),
    )

    def test_parses_typed_directed_matrix_and_skips_unreachable_pairs(self):
        session = FakeSession(
            FakeResponse(
                {
                    "sources_to_targets": [
                        [
                            {"time": 0, "distance": 0},
                            {"time": 65.2, "distance": 1.234},
                        ],
                        [
                            {"time": None, "distance": None},
                            {"time": 0, "distance": 0},
                        ],
                    ]
                }
            )
        )
        client = ValhallaMatrixClient(
            "https://routing.example.com/valhalla/",
            session=session,
        )

        result = client.fetch_matrix(self.locations, transport="drive")

        self.assertEqual(result.provider, "valhalla")
        self.assertEqual(result.source_url, "https://routing.example.com/valhalla")
        self.assertEqual(len(result.values), 1)
        value = result.values[0]
        self.assertEqual(value.origin_spot_id, 1)
        self.assertEqual(value.destination_spot_id, 2)
        self.assertEqual(value.duration_seconds, 66)
        self.assertEqual(value.distance_metres, 1234)
        _url, kwargs = session.calls[0]
        self.assertEqual(kwargs["json"]["costing"], "auto")
        self.assertEqual(kwargs["json"]["units"], "kilometers")

    def test_rejects_unsafe_configuration_and_malformed_dimensions(self):
        unsafe = (
            "http://routing.example.com",
            "https://user:password@routing.example.com",
            "https://routing.example.com?token=secret",
        )
        for url in unsafe:
            with self.subTest(url=url), self.assertRaises(ProviderConfigurationError):
                ValhallaMatrixClient(url)

        client = ValhallaMatrixClient(
            "https://routing.example.com",
            session=FakeSession(FakeResponse({"sources_to_targets": [[]]})),
        )
        with self.assertRaises(ProviderPayloadError):
            client.fetch_matrix(self.locations, transport="walk")

    def test_transport_failures_are_sanitized(self):
        client = ValhallaMatrixClient(
            "https://routing.example.com",
            session=FakeSession(error=True),
        )
        with self.assertRaises(ProviderTransportError) as raised:
            client.fetch_matrix(self.locations, transport="bicycle")
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("token", str(raised.exception))
