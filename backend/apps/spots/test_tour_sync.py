"""No-network tests for conservative TourAPI WaterSpot enrichment."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.spots.models import WaterSpot
from services.catalog import CatalogEnrichmentError, TourSpotEnrichmentService
from services.providers.base import ProviderResult
from services.providers.tour_api import TourApiClient, TourPlaceDetail


COMMAND_MODULE = "apps.spots.management.commands.sync_tour_spots"
TEST_CREDENTIAL = "test-only-provider-credential"
SOURCE_ENDPOINT = "/B551011/KorService2/detailCommon2"
PROVIDER_MODIFIED_AT = datetime(
    2026,
    8,
    16,
    12,
    0,
    tzinfo=timezone.get_current_timezone(),
)


def tour_detail(
    content_id: str,
    *,
    title: str | None = "경포해변",
    address: str | None = "강원특별자치도 강릉시",
    detail_address: str | None = "창해로 514",
    latitude: Decimal | None = Decimal("37.8057"),
    longitude: Decimal | None = Decimal("128.9075"),
    image_url: str | None = "https://images.example.test/gyeongpo.jpg",
    thumbnail_url: str | None = None,
    overview: str | None = "<p>고요한 <strong>바다</strong>입니다.</p>",
    modified_at: datetime | None = PROVIDER_MODIFIED_AT,
) -> TourPlaceDetail:
    return TourPlaceDetail(
        content_id=content_id,
        content_type_id="12",
        title=title,
        address=address,
        detail_address=detail_address,
        latitude=latitude,
        longitude=longitude,
        image_url=image_url,
        thumbnail_url=thumbnail_url,
        telephone=None,
        homepage=None,
        overview=overview,
        modified_at=modified_at,
    )


def provider_result(
    detail: TourPlaceDetail,
    *,
    endpoint: str = SOURCE_ENDPOINT,
) -> ProviderResult[TourPlaceDetail]:
    return ProviderResult(
        provider="TourAPI",
        endpoint=endpoint,
        records=(detail,),
        reported_total_count=1,
    )


class FakeTourClient:
    def __init__(
        self,
        responses: dict[str, ProviderResult[TourPlaceDetail]],
        *,
        language: str = "ko",
    ) -> None:
        self.responses = responses
        self.language = language
        self.calls: list[str] = []

    def fetch_detail(self, content_id: str) -> ProviderResult[TourPlaceDetail]:
        self.calls.append(content_id)
        return self.responses[content_id]


def water_spot(
    *,
    name: str = "",
    address: str = "",
    lat: float = 0.0,
    lng: float = 0.0,
    tourapi_id: str = "100",
    image_url: str = "",
    description: str = "",
) -> WaterSpot:
    return WaterSpot.objects.create(
        type="beach",
        name=name,
        lat=lat,
        lng=lng,
        tourapi_id=tourapi_id,
        region="강원",
        address=address,
        image_url=image_url,
        description=description,
    )


class TourSpotEnrichmentServiceTests(TestCase):
    def test_only_existing_curated_spot_is_enriched_with_sanitized_values(self) -> None:
        spot = water_spot(tourapi_id="100")
        hostile_overview = (
            "<p>고요한 <b>바다</b></p>"
            "<script>stealCredential()</script>"
            "<style>body{display:none}</style>"
            "&lt;script&gt;encodedAttack()&lt;/script&gt;"
            "<div>가족 여행&nbsp;추천</div>"
        )
        result = provider_result(
            tour_detail("100", overview=hostile_overview),
            endpoint=(
                "https://apis.data.go.kr/B551011/KorService2/detailCommon2"
                f"?serviceKey={TEST_CREDENTIAL}"
            ),
        )
        client = FakeTourClient({"100": result})

        report = TourSpotEnrichmentService(client).sync((spot,))

        spot.refresh_from_db()
        self.assertEqual(WaterSpot.objects.count(), 1)
        self.assertEqual(client.calls, ["100"])
        self.assertEqual(spot.name, "경포해변")
        self.assertEqual(spot.address, "강원특별자치도 강릉시 창해로 514")
        self.assertEqual(spot.lat, 37.8057)
        self.assertEqual(spot.lng, 128.9075)
        self.assertEqual(
            spot.image_url,
            "https://images.example.test/gyeongpo.jpg",
        )
        self.assertEqual(spot.description, "고요한 바다 가족 여행 추천")
        self.assertNotIn("script", spot.description.casefold())
        self.assertNotIn("attack", spot.description.casefold())
        self.assertNotIn("<", spot.description)
        self.assertEqual(spot.catalog_source, "TourAPI")
        self.assertEqual(spot.catalog_source_url, TourApiClient.SOURCE_URL)
        self.assertEqual(spot.catalog_verified_at, PROVIDER_MODIFIED_AT)
        self.assertEqual(
            spot.catalog_verification,
            WaterSpot.VerificationState.VERIFIED,
        )
        self.assertEqual(
            report.results[0].changed_fields,
            (
                "name",
                "address",
                "lat",
                "lng",
                "image_url",
                "description",
                "catalog_source",
                "catalog_source_url",
                "catalog_verified_at",
                "catalog_verification",
            ),
        )
        provenance = report.results[0].provenance
        self.assertIsNotNone(provenance)
        self.assertEqual(provenance.endpoint, SOURCE_ENDPOINT)  # type: ignore[union-attr]
        self.assertNotIn(TEST_CREDENTIAL, repr(report))
        self.assertEqual(provenance.provider, "TourAPI")  # type: ignore[union-attr]
        self.assertTrue(provenance.public_source_url.startswith("https://"))  # type: ignore[union-attr]

    def test_existing_fields_are_preserved_unless_overwrite_is_explicit(self) -> None:
        spot = water_spot(
            name="수동 이름",
            address="수동 주소",
            lat=37.1,
            lng=128.1,
            tourapi_id="200",
            image_url="https://curated.example.test/image.jpg",
            description="수동 설명",
        )
        client = FakeTourClient({"200": provider_result(tour_detail("200"))})
        service = TourSpotEnrichmentService(client)

        preserved = service.sync((spot,))
        spot.refresh_from_db()
        self.assertEqual(preserved.results[0].status, "updated")
        self.assertEqual(
            preserved.results[0].changed_fields,
            (
                "catalog_source",
                "catalog_source_url",
                "catalog_verified_at",
                "catalog_verification",
            ),
        )
        self.assertEqual(spot.name, "수동 이름")
        self.assertEqual(spot.address, "수동 주소")
        self.assertEqual(spot.lat, 37.1)
        self.assertEqual(spot.image_url, "https://curated.example.test/image.jpg")
        self.assertEqual(spot.description, "수동 설명")
        self.assertEqual(spot.catalog_source, "TourAPI")
        self.assertEqual(spot.catalog_verified_at, PROVIDER_MODIFIED_AT)

        replaced = service.sync((spot,), overwrite=True)
        spot.refresh_from_db()
        self.assertEqual(replaced.results[0].status, "updated")
        self.assertEqual(spot.name, "경포해변")
        self.assertEqual(spot.address, "강원특별자치도 강릉시 창해로 514")
        self.assertEqual(spot.lat, 37.8057)
        self.assertEqual(spot.lng, 128.9075)
        self.assertEqual(spot.description, "고요한 바다입니다.")

        repeated = service.sync((spot,), overwrite=True)
        self.assertEqual(repeated.results[0].status, "unchanged")
        self.assertEqual(repeated.results[0].changed_fields, ())

    def test_dry_run_does_not_write_and_missing_tourapi_id_is_skipped(self) -> None:
        curated = water_spot(tourapi_id="300")
        unlinked = water_spot(tourapi_id="")
        client = FakeTourClient({"300": provider_result(tour_detail("300"))})

        report = TourSpotEnrichmentService(client).sync(
            (unlinked, curated),
            dry_run=True,
        )

        curated.refresh_from_db()
        unlinked.refresh_from_db()
        self.assertEqual(curated.name, "")
        self.assertEqual(curated.catalog_source, "")
        self.assertIsNone(curated.catalog_verified_at)
        self.assertEqual(
            curated.catalog_verification,
            WaterSpot.VerificationState.UNKNOWN,
        )
        self.assertEqual(unlinked.name, "")
        self.assertEqual(client.calls, ["300"])
        statuses = {result.spot_id: result.status for result in report.results}
        self.assertEqual(statuses[curated.pk], "would_update")
        self.assertEqual(statuses[unlinked.pk], "skipped_missing_tourapi_id")
        self.assertTrue(report.dry_run)

    def test_wrong_content_id_fails_before_any_write(self) -> None:
        first = water_spot(tourapi_id="401")
        second = water_spot(tourapi_id="402")
        client = FakeTourClient(
            {
                "401": provider_result(tour_detail("401", title="첫 장소")),
                "402": provider_result(tour_detail("different", title="잘못된 장소")),
            }
        )

        with self.assertRaisesRegex(CatalogEnrichmentError, "different content id"):
            TourSpotEnrichmentService(client).sync((first, second))

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.name, "")
        self.assertEqual(second.name, "")
        self.assertEqual(first.catalog_source, "")
        self.assertEqual(second.catalog_source, "")
        self.assertEqual(WaterSpot.objects.count(), 2)

    def test_missing_provider_modified_time_is_persisted_as_partial(self) -> None:
        spot = water_spot(tourapi_id="450")
        client = FakeTourClient(
            {
                "450": provider_result(
                    tour_detail("450", modified_at=None),
                )
            }
        )

        first = TourSpotEnrichmentService(client).sync((spot,))
        spot.refresh_from_db()

        self.assertEqual(first.results[0].status, "updated")
        self.assertEqual(spot.catalog_source, "TourAPI")
        self.assertEqual(spot.catalog_source_url, TourApiClient.SOURCE_URL)
        self.assertIsNone(spot.catalog_verified_at)
        self.assertEqual(
            spot.catalog_verification,
            WaterSpot.VerificationState.PARTIAL,
        )

        second = TourSpotEnrichmentService(client).sync((spot,))
        self.assertEqual(second.results[0].status, "unchanged")
        self.assertEqual(second.results[0].changed_fields, ())

    def test_duplicate_normalized_tourapi_ids_fail_before_provider_calls(self) -> None:
        first = water_spot(tourapi_id="duplicate-id")
        second = water_spot(tourapi_id=" duplicate-id ")
        client = FakeTourClient({})

        with self.assertRaisesRegex(CatalogEnrichmentError, "manual identifier audit"):
            TourSpotEnrichmentService(client).sync((first, second))

        self.assertEqual(client.calls, [])

    def test_invalid_provider_time_fails_before_any_database_write(self) -> None:
        first = water_spot(tourapi_id="451")
        second = water_spot(tourapi_id="452")
        client = FakeTourClient(
            {
                "451": provider_result(tour_detail("451", title="첫 장소")),
                "452": provider_result(
                    tour_detail(
                        "452",
                        title="둘째 장소",
                        modified_at=datetime(2026, 8, 16, 12, 0),
                    )
                ),
            }
        )

        with self.assertRaisesRegex(CatalogEnrichmentError, "invalid modification time"):
            TourSpotEnrichmentService(client).sync((first, second))

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.name, "")
        self.assertEqual(second.name, "")
        self.assertEqual(first.catalog_source, "")
        self.assertEqual(second.catalog_source, "")

    def test_only_absolute_credential_free_https_images_are_stored(self) -> None:
        spot = water_spot(tourapi_id="500")
        client = FakeTourClient(
            {
                "500": provider_result(
                    tour_detail(
                        "500",
                        image_url="https://user:password@images.example.test/a.jpg",
                        thumbnail_url="http://images.example.test/a.jpg",
                    )
                )
            }
        )

        TourSpotEnrichmentService(client).sync((spot,))

        spot.refresh_from_db()
        self.assertEqual(spot.image_url, "")

        spot_with_query_credential = water_spot(tourapi_id="501")
        query_client = FakeTourClient(
            {
                "501": provider_result(
                    tour_detail(
                        "501",
                        image_url=(
                            "https://images.example.test/a.jpg"
                            f"?serviceKey={TEST_CREDENTIAL}"
                        ),
                    )
                )
            }
        )
        TourSpotEnrichmentService(query_client).sync((spot_with_query_credential,))
        spot_with_query_credential.refresh_from_db()
        self.assertEqual(spot_with_query_credential.image_url, "")

    def test_database_updates_are_all_or_nothing(self) -> None:
        first = water_spot(tourapi_id="601")
        second = water_spot(tourapi_id="602")
        client = FakeTourClient(
            {
                "601": provider_result(tour_detail("601", title="첫 장소")),
                "602": provider_result(tour_detail("602", title="둘째 장소")),
            }
        )
        original_save = WaterSpot.save

        def fail_second_save(instance: WaterSpot, *args: Any, **kwargs: Any) -> None:
            if instance.pk == second.pk:
                raise RuntimeError("simulated persistence failure")
            original_save(instance, *args, **kwargs)

        with patch.object(WaterSpot, "save", new=fail_second_save):
            with self.assertRaises(RuntimeError):
                TourSpotEnrichmentService(client).sync((first, second))

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.name, "")
        self.assertEqual(second.name, "")
        self.assertEqual(first.catalog_source, "")
        self.assertEqual(second.catalog_source, "")


class _FakeHttpResponse:
    status_code = 200
    headers: dict[str, str] = {}

    def __init__(self, content_id: str) -> None:
        self._content_id = content_id

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "response": {
                "header": {"resultCode": "0000", "resultMsg": "OK"},
                "body": {
                    "totalCount": 1,
                    "items": {"item": {"contentid": self._content_id}},
                },
            }
        }


class _RecordingSession:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str, **kwargs: Any) -> _FakeHttpResponse:
        self.urls.append(url)
        return _FakeHttpResponse(str(kwargs["params"]["contentId"]))


class TourApiLanguageContractTests(TestCase):
    def test_every_command_language_maps_to_its_service2_detail_gateway(self) -> None:
        gateways = {
            "ko": "KorService2",
            "en": "EngService2",
            "ja": "JpnService2",
            "zh-hans": "ChsService2",
            "zh-hant": "ChtService2",
        }
        for language, gateway in gateways.items():
            with self.subTest(language=language):
                session = _RecordingSession()
                client = TourApiClient(
                    TEST_CREDENTIAL,
                    language=language,
                    session=session,
                    max_retries=0,
                )
                result = client.fetch_detail("700")
                self.assertEqual(result.records[0].content_id, "700")
                self.assertEqual(
                    session.urls,
                    [
                        "https://apis.data.go.kr/"
                        f"B551011/{gateway}/detailCommon2"
                    ],
                )


class SyncTourSpotsCommandTests(TestCase):
    def setUp(self) -> None:
        self.curated = water_spot(tourapi_id="800")
        self.unlinked = water_spot(tourapi_id="")

    @patch(f"{COMMAND_MODULE}.TourApiClient")
    @patch(f"{COMMAND_MODULE}.ProviderConfig.from_environment")
    def test_repeatable_spot_language_overwrite_and_dry_run_use_env_only(
        self,
        from_environment: MagicMock,
        client_class: MagicMock,
    ) -> None:
        from_environment.return_value = SimpleNamespace(tour_api=TEST_CREDENTIAL)
        client = client_class.return_value
        client.language = "ja"
        client.fetch_detail.return_value = provider_result(
            tour_detail("800"),
            endpoint=(
                "/B551011/JpnService2/detailCommon2"
                f"?serviceKey={TEST_CREDENTIAL}"
            ),
        )
        stdout = StringIO()

        call_command(
            "sync_tour_spots",
            "--spot",
            str(self.curated.pk),
            "--spot",
            str(self.unlinked.pk),
            "--language",
            "ja",
            "--overwrite",
            "--dry-run",
            stdout=stdout,
        )

        client_class.assert_called_once_with(TEST_CREDENTIAL, language="ja")
        client.fetch_detail.assert_called_once_with("800")
        client.close.assert_called_once_with()
        self.curated.refresh_from_db()
        self.assertEqual(self.curated.name, "")
        output = stdout.getvalue()
        self.assertIn("status=would_update", output)
        self.assertIn("status=skipped_missing_tourapi_id", output)
        self.assertIn("dry-run", output)
        self.assertNotIn(TEST_CREDENTIAL, output)

    @patch(f"{COMMAND_MODULE}.TourApiClient")
    @patch(f"{COMMAND_MODULE}.ProviderConfig.from_environment")
    def test_default_selection_never_fetches_unlinked_spots(
        self,
        from_environment: MagicMock,
        client_class: MagicMock,
    ) -> None:
        from_environment.return_value = SimpleNamespace(tour_api=TEST_CREDENTIAL)
        client = client_class.return_value
        client.language = "ko"
        client.fetch_detail.return_value = provider_result(tour_detail("800"))

        call_command("sync_tour_spots", "--dry-run", stdout=StringIO())

        client.fetch_detail.assert_called_once_with("800")
        self.assertEqual(WaterSpot.objects.count(), 2)

    def test_identifier_audit_needs_no_credentials_and_makes_no_changes(self) -> None:
        stdout = StringIO()
        with (
            patch(f"{COMMAND_MODULE}.ProviderConfig.from_environment") as config,
            patch(f"{COMMAND_MODULE}.TourApiClient") as client_class,
        ):
            call_command(
                "sync_tour_spots",
                "--audit-identifiers",
                stdout=stdout,
            )

        config.assert_not_called()
        client_class.assert_not_called()
        self.curated.refresh_from_db()
        self.assertEqual(self.curated.name, "")
        self.assertIn("identifier audit passed", stdout.getvalue())

    def test_identifier_audit_reports_counts_without_values_or_changes(self) -> None:
        duplicate_counts = {
            "tourapi_id": 1,
            "khoa_beach_code": 2,
        }
        with (
            patch(
                f"{COMMAND_MODULE}._duplicate_identifier_group_counts",
                return_value=duplicate_counts,
            ),
            patch(f"{COMMAND_MODULE}.ProviderConfig.from_environment") as config,
            patch(f"{COMMAND_MODULE}.TourApiClient") as client_class,
        ):
            with self.assertRaises(CommandError) as raised:
                call_command("sync_tour_spots", "--audit-identifiers")

        message = str(raised.exception)
        self.assertIn("tourapi_id groups=1", message)
        self.assertIn("khoa_beach_code groups=2", message)
        self.assertIn("no rows were changed", message)
        self.assertNotIn(self.curated.tourapi_id, message)
        config.assert_not_called()
        client_class.assert_not_called()

    @patch(f"{COMMAND_MODULE}.TourApiClient")
    @patch(f"{COMMAND_MODULE}.ProviderConfig.from_environment")
    def test_missing_credential_fails_before_client_creation(
        self,
        from_environment: MagicMock,
        client_class: MagicMock,
    ) -> None:
        from_environment.return_value = SimpleNamespace(tour_api="")

        with self.assertRaisesMessage(
            CommandError,
            "TourAPI provider credential is not configured",
        ):
            call_command("sync_tour_spots")

        client_class.assert_not_called()

    @patch(f"{COMMAND_MODULE}.TourApiClient")
    @patch(f"{COMMAND_MODULE}.ProviderConfig.from_environment")
    def test_unexpected_provider_error_cannot_leak_credential(
        self,
        from_environment: MagicMock,
        client_class: MagicMock,
    ) -> None:
        from_environment.return_value = SimpleNamespace(tour_api=TEST_CREDENTIAL)
        client = client_class.return_value
        client.language = "ko"
        client.fetch_detail.side_effect = RuntimeError(
            f"prepared URL serviceKey={TEST_CREDENTIAL}"
        )

        with self.assertRaises(CommandError) as raised:
            call_command("sync_tour_spots", "--spot", str(self.curated.pk))

        self.assertEqual(
            str(raised.exception),
            "TourAPI WaterSpot synchronization failed internally",
        )
        self.assertNotIn(TEST_CREDENTIAL, str(raised.exception))
        client.close.assert_called_once_with()

    @patch(f"{COMMAND_MODULE}.TourApiClient")
    @patch(f"{COMMAND_MODULE}.ProviderConfig.from_environment")
    def test_configuration_failure_cannot_leak_credential(
        self,
        from_environment: MagicMock,
        client_class: MagicMock,
    ) -> None:
        from_environment.side_effect = RuntimeError(
            f"configuration source contained {TEST_CREDENTIAL}"
        )

        with self.assertRaises(CommandError) as raised:
            call_command("sync_tour_spots")

        self.assertEqual(
            str(raised.exception),
            "TourAPI WaterSpot synchronization failed internally",
        )
        self.assertNotIn(TEST_CREDENTIAL, str(raised.exception))
        client_class.assert_not_called()
