from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.spots.models import WaterSpot


class GangneungCatalogBootstrapTests(TestCase):
    def test_bootstrap_creates_only_reviewed_identifiers_and_is_idempotent(self):
        call_command("bootstrap_gangneung_catalog", stdout=StringIO())
        call_command("bootstrap_gangneung_catalog", stdout=StringIO())

        rows = WaterSpot.objects.filter(region__icontains="강릉")
        self.assertEqual(
            set(rows.values_list("name", flat=True)),
            {"경포해변", "안목해변", "사천진해변"},
        )
        gyeongpo = rows.get(name="경포해변")
        self.assertEqual(gyeongpo.khoa_beach_code, "GYEONGPO")
        self.assertEqual(gyeongpo.catalog_verification, "verified")
        self.assertTrue(gyeongpo.catalog_source_url.startswith("https://"))
        self.assertFalse(
            rows.exclude(name="경포해변").exclude(khoa_beach_code="").exists()
        )

    def test_existing_operator_row_is_never_overwritten(self):
        existing = WaterSpot.objects.create(
            type="beach",
            name="경포해변",
            lat=37.8,
            lng=128.9,
            region="강릉시 운영 catalog",
            address="운영자가 검증한 주소",
            catalog_source="LOCAL_OPERATOR",
        )

        call_command("bootstrap_gangneung_catalog", stdout=StringIO())
        existing.refresh_from_db()

        self.assertEqual(existing.address, "운영자가 검증한 주소")
        self.assertEqual(existing.catalog_source, "LOCAL_OPERATOR")
        self.assertEqual(existing.khoa_beach_code, "")

    def test_dry_run_writes_nothing(self):
        call_command(
            "bootstrap_gangneung_catalog",
            dry_run=True,
            stdout=StringIO(),
        )
        self.assertFalse(WaterSpot.objects.exists())
