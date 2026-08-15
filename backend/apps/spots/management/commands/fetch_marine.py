from apps.spots.management.commands._common import PublicFetchCommand
from services.conditions_sync import sync_marine


class Command(PublicFetchCommand):
    help = "Fetch KHOA tide, temperature, beach/surf/mudflat index, rip current, and wave."

    def handle_spot(self, spot, dry_run):
        return sync_marine(spot, dry_run=dry_run)
