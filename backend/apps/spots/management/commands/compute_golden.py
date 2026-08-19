from django.core.management.base import BaseCommand

from apps.spots.models import WaterSpot
from services.persist_content import persist_spot_content


class Command(BaseCommand):
    help = "Compute ASMR, golden calendar, and analytics from stored conditions."

    def add_arguments(self, parser):
        parser.add_argument("--spot-id", type=int)

    def handle(self, *args, **options):
        spots = WaterSpot.objects.all()
        if options.get("spot_id"):
            spots = spots.filter(pk=options["spot_id"])
        count = 0
        for spot in spots:
            persist_spot_content(spot)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Computed content for {count} spots."))
