from apps.spots.management.commands._common import PublicFetchCommand
from services.conditions_sync import sync_quality


class Command(PublicFetchCommand):
    help = "Fetch MOE/NIER water-quality grades for mapped inland spots."

    def handle_spot(self, spot, dry_run):
        return sync_quality(spot, dry_run=dry_run)
