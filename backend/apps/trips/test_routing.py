from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.spots.models import WaterSpot
from apps.trips.models import RouteMatrixEntry, RouteMatrixSnapshot
from services.providers.valhalla import RouteMatrixResult, RouteMatrixValue
from services.routing import DatabaseTravelTimeProvider, persist_route_matrix


class RouteMatrixPersistenceTests(TestCase):
    def setUp(self):
        self.now = timezone.now().replace(second=0, microsecond=0)
        self.first = self.spot("출발")
        self.second = self.spot("도착")

    @staticmethod
    def spot(name):
        return WaterSpot.objects.create(
            type="beach",
            name=name,
            lat=37.8,
            lng=128.9,
            region="강릉",
            address="강릉시",
        )

    def result(self, seconds=61):
        return RouteMatrixResult(
            provider="valhalla",
            source_url="https://routing.example.com",
            transport="drive",
            values=(
                RouteMatrixValue(
                    self.first.pk,
                    self.second.pk,
                    seconds,
                    1_000,
                ),
                RouteMatrixValue(
                    self.second.pk,
                    self.first.pk,
                    seconds + 30,
                    1_100,
                ),
            ),
        )

    def test_persistence_deduplicates_and_current_lookup_rounds_up(self):
        snapshot, created = persist_route_matrix(
            self.result(),
            observed_at=self.now,
            fetched_at=self.now,
            valid_for=timedelta(hours=24),
            spot_ids=(self.first.pk, self.second.pk),
        )
        duplicate, duplicate_created = persist_route_matrix(
            self.result(),
            observed_at=self.now,
            fetched_at=self.now + timedelta(seconds=30),
            valid_for=timedelta(hours=24),
            spot_ids=(self.first.pk, self.second.pk),
        )

        provider = DatabaseTravelTimeProvider.current(
            spot_ids=(self.first.pk, self.second.pk),
            transport="drive",
            at=self.now + timedelta(minutes=1),
        )
        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(duplicate.pk, snapshot.pk)
        self.assertEqual(RouteMatrixSnapshot.objects.count(), 1)
        self.assertEqual(RouteMatrixEntry.objects.count(), 2)
        self.assertEqual(
            provider.minutes(str(self.first.pk), str(self.second.pk)),
            2,
        )
        self.assertEqual(provider.minutes(str(self.first.pk), str(self.first.pk)), 0)
        self.assertEqual(provider.evidence.snapshot_ids, (snapshot.pk,))
        self.assertEqual(provider.evidence.available_pairs, 2)

    def test_expired_or_wrong_transport_evidence_is_not_used(self):
        persist_route_matrix(
            self.result(),
            observed_at=self.now - timedelta(days=2),
            fetched_at=self.now - timedelta(days=2),
            valid_for=timedelta(hours=1),
            spot_ids=(self.first.pk, self.second.pk),
        )
        provider = DatabaseTravelTimeProvider.current(
            spot_ids=(self.first.pk, self.second.pk),
            transport="walk",
            at=self.now,
        )
        self.assertIsNone(provider.minutes(str(self.first.pk), str(self.second.pk)))
        self.assertEqual(provider.evidence.snapshot_ids, ())

    def test_duplicate_or_out_of_scope_pairs_roll_back_the_snapshot(self):
        invalid = RouteMatrixResult(
            provider="valhalla",
            source_url="https://routing.example.com",
            transport="drive",
            values=(
                RouteMatrixValue(self.first.pk, self.second.pk, 60, 1_000),
                RouteMatrixValue(self.first.pk, self.second.pk, 70, 1_000),
            ),
        )
        with self.assertRaises(ValueError):
            persist_route_matrix(
                invalid,
                observed_at=self.now,
                fetched_at=self.now,
                valid_for=timedelta(hours=1),
                spot_ids=(self.first.pk, self.second.pk),
            )
        self.assertFalse(RouteMatrixSnapshot.objects.exists())
