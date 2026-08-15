from django.core.management.base import BaseCommand

from apps.spots.management.commands._common import add_spot_arguments, iter_spots
from services.conditions_sync import sync_marine, sync_tour, sync_weather
from services.public_data import PublicDataError
from services.water_forecast import upsert_forecast_for_spot
from services.water_index import upsert_scores_for_spot


class Command(BaseCommand):
    help = "Fetch public APIs, then recompute Water Index and 7-day forecast."

    def add_arguments(self, parser):
        add_spot_arguments(parser)
        parser.add_argument("--skip-tour", action="store_true")

    def handle(self, *args, **options):
        spots = list(iter_spots(options.get("spot_id")))
        if not spots:
            self.stdout.write(self.style.WARNING("No spots found."))
            return

        dry_run = options["dry_run"]
        for spot in spots:
            for label, func, enabled in (
                ("weather", sync_weather, True),
                ("marine", sync_marine, True),
                ("tour", sync_tour, not options["skip_tour"]),
            ):
                if not enabled:
                    continue
                try:
                    result = func(spot, dry_run=dry_run)
                except PublicDataError as exc:
                    self.stderr.write(f"{spot.name} {label}: {exc}")
                    continue
                if result.get("skipped"):
                    continue
                self.stdout.write(f"{spot.name} {label}: {'dry-run' if dry_run else 'ok'}")

            if dry_run:
                continue
            upsert_scores_for_spot(spot)
            upsert_forecast_for_spot(spot)

        self.stdout.write(self.style.SUCCESS(f"Refreshed {len(spots)} spots."))
