from apps.spots.management.commands._common import PublicFetchCommand
from services.conditions_sync import sync_tour


class Command(PublicFetchCommand):
    help = "Enrich seed spots with TourAPI image, id, and overview."

    def handle_spot(self, spot, dry_run):
        return sync_tour(spot, dry_run=dry_run)
