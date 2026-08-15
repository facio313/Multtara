from apps.spots.management.commands._common import PublicFetchCommand
from services.conditions_sync import sync_weather


class Command(PublicFetchCommand):
    help = "Fetch KMA observation and 7-day outlook for spots."

    def handle_spot(self, spot, dry_run):
        return sync_weather(spot, dry_run=dry_run)
