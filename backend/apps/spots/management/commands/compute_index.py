from django.core.management.base import BaseCommand

from apps.spots.models import WaterSpot
from services.water_forecast import upsert_forecast_for_spot
from services.water_index import upsert_scores_for_spot


class Command(BaseCommand):
    help = "Recompute Water Index and 7-day forecast from stored conditions."

    def add_arguments(self, parser):
        parser.add_argument("--spot-id", type=int)

    def handle(self, *args, **options):
        spots = WaterSpot.objects.all()
        if options.get("spot_id"):
            spots = spots.filter(pk=options["spot_id"])
        count = 0
        for spot in spots:
            upsert_scores_for_spot(spot)
            upsert_forecast_for_spot(spot)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Recomputed index/forecast for {count} spots."))
