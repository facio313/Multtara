from __future__ import annotations

import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from services.ingestion.kma_adapter import KmaAdapterError, adapt_weather_values
from services.ingestion.weather import (
    KmaMode,
    WeatherIngestionService,
    latest_available_issue,
)
from services.providers.base import ProviderResult
from services.providers.kma import KmaClient, WeatherValue, latlon_to_grid


KST = ZoneInfo("Asia/Seoul")


def value(category: str, raw: Decimal | str | None, *, valid_hour: int = 14):
    return WeatherValue(
        category=category,
        value=raw,
        unit="provider_value",
        issued_at=datetime(2026, 8, 16, 13, tzinfo=KST),
        valid_at=datetime(2026, 8, 16, valid_hour, tzinfo=KST),
        grid_x=92,
        grid_y=132,
    )


class KmaAdapterTests(unittest.TestCase):
    def test_forecast_maps_only_documented_weather_without_clearing_safety(self) -> None:
        observation = adapt_weather_values(
            (
                value("TMP", Decimal("27.4")),
                value("WSD", Decimal("3.2")),
                value("POP", Decimal("30")),
                value("PTY", "0"),
                value("LGT", "0"),
            ),
            fetched_at=datetime(2026, 8, 16, 13, 10, tzinfo=KST),
            endpoint=KmaClient.SHORT_FORECAST_ENDPOINT,
            forecast=True,
        )[0]

        self.assertEqual(observation.provider, "KMA")
        self.assertEqual(observation.state, "live")
        self.assertEqual(
            observation.valid_until,
            datetime(2026, 8, 16, 15, tzinfo=KST),
        )
        self.assertEqual(
            observation.observations.get("air_temperature_c").value, 27.4
        )
        self.assertEqual(
            observation.observations.get("lightning_category_code").value, "0"
        )
        emitted = set(observation.observations.metrics)
        self.assertTrue(
            emitted.isdisjoint(
                {
                    "weather_alert_level",
                    "lightning_clearance_minutes",
                    "marine_hazard_status",
                    "official_entry_status",
                }
            )
        )
        self.assertNotIn("?", observation.source_url)
        self.assertNotIn("?", observation.observations.get("air_temperature_c").source_url)

    def test_values_are_grouped_by_valid_time_and_unknown_categories_are_ignored(self) -> None:
        observations = adapt_weather_values(
            (
                value("TMP", Decimal("27"), valid_hour=14),
                value("UNKNOWN", "secret-shaped-provider-field", valid_hour=14),
                value("TMP", Decimal("25"), valid_hour=15),
            ),
            fetched_at=datetime(2026, 8, 16, 13, 5, tzinfo=KST),
            endpoint=KmaClient.SHORT_FORECAST_ENDPOINT,
            forecast=True,
        )

        self.assertEqual(len(observations), 2)
        self.assertEqual(
            [item.observations.get("air_temperature_c").value for item in observations],
            [27.0, 25.0],
        )
        self.assertNotIn("UNKNOWN", repr(observations))

    def test_future_nowcast_and_naive_fetch_fail_closed(self) -> None:
        record = WeatherValue(
            category="T1H",
            value=Decimal("26"),
            unit="celsius",
            issued_at=datetime(2026, 8, 16, 14, tzinfo=KST),
            valid_at=datetime(2026, 8, 16, 14, tzinfo=KST),
            grid_x=92,
            grid_y=132,
        )
        with self.assertRaises(KmaAdapterError):
            adapt_weather_values(
                (record,),
                fetched_at=datetime(2026, 8, 16, 13, 59, tzinfo=KST),
                endpoint=KmaClient.NOWCAST_ENDPOINT,
                forecast=False,
            )
        with self.assertRaisesRegex(KmaAdapterError, "timezone-aware"):
            adapt_weather_values(
                (),
                fetched_at=datetime(2026, 8, 16, 14),
                endpoint=KmaClient.NOWCAST_ENDPOINT,
                forecast=False,
            )

    def test_latest_available_issue_respects_provider_publication_lags(self) -> None:
        self.assertEqual(
            latest_available_issue(
                KmaMode.NOWCAST, datetime(2026, 8, 16, 14, 39, tzinfo=KST)
            ),
            datetime(2026, 8, 16, 13, tzinfo=KST),
        )
        self.assertEqual(
            latest_available_issue(
                KmaMode.ULTRA_SHORT,
                datetime(2026, 8, 16, 14, 44, tzinfo=KST),
            ),
            datetime(2026, 8, 16, 13, 30, tzinfo=KST),
        )
        self.assertEqual(
            latest_available_issue(
                KmaMode.SHORT, datetime(2026, 8, 16, 14, 10, tzinfo=KST)
            ),
            datetime(2026, 8, 16, 11, tzinfo=KST),
        )


class FakeKmaClient:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def fetch_nowcast(self, *, issued_at, grid_x, grid_y):
        self.calls.append((grid_x, grid_y))
        record = WeatherValue(
            category="T1H",
            value=Decimal("26"),
            unit="celsius",
            issued_at=issued_at,
            valid_at=issued_at,
            grid_x=grid_x,
            grid_y=grid_y,
        )
        return ProviderResult(
            provider="KMA",
            endpoint=KmaClient.NOWCAST_ENDPOINT,
            records=(record,),
            reported_total_count=1,
        )


class WeatherIngestionServiceTests(unittest.TestCase):
    def test_shared_grid_is_fetched_once_and_dry_run_never_persists(self) -> None:
        client = FakeKmaClient()
        persisted: list[object] = []
        service = WeatherIngestionService(
            client,  # type: ignore[arg-type]
            persister=lambda **kwargs: persisted.append(kwargs),  # type: ignore[arg-type]
            clock=lambda: datetime(2026, 8, 16, 13, 50, tzinfo=KST),
        )
        spots = (
            SimpleNamespace(pk=1, lat=37.8055, lng=128.9070),
            SimpleNamespace(pk=2, lat=37.8060, lng=128.9075),
        )

        report = service.sync(
            mode=KmaMode.NOWCAST,
            issued_at=datetime(2026, 8, 16, 13, tzinfo=KST),
            spots=spots,
            dry_run=True,
        )

        expected_grid = latlon_to_grid(spots[0].lat, spots[0].lng)
        self.assertEqual(client.calls, [(expected_grid.x, expected_grid.y)])
        self.assertEqual(report.requested_grids, 1)
        self.assertEqual(report.normalized_snapshots, 2)
        self.assertEqual(report.persisted_snapshots, 0)
        self.assertEqual(persisted, [])


if __name__ == "__main__":
    unittest.main()
