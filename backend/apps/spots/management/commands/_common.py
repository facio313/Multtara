from django.core.management.base import BaseCommand

from apps.spots.models import WaterSpot
from services.public_data import PublicDataError


def add_spot_arguments(parser):
    parser.add_argument("--spot-id", type=int)
    parser.add_argument("--dry-run", action="store_true")


def iter_spots(spot_id=None):
    queryset = WaterSpot.objects.all().order_by("id")
    if spot_id:
        queryset = queryset.filter(pk=spot_id)
    return queryset


class PublicFetchCommand(BaseCommand):
    def add_arguments(self, parser):
        add_spot_arguments(parser)

    def handle_spot(self, spot, dry_run):
        raise NotImplementedError

    def handle(self, *args, **options):
        spots = list(iter_spots(options.get("spot_id")))
        if not spots:
            self.stdout.write(self.style.WARNING("No spots found."))
            return
        ok = 0
        skipped = 0
        failed = 0
        for spot in spots:
            try:
                result = self.handle_spot(spot, options["dry_run"])
            except PublicDataError as exc:
                failed += 1
                self.stderr.write(f"{spot.name}: {exc}")
                continue
            if result.get("skipped"):
                skipped += 1
                self.stdout.write(f"{spot.name}: skipped ({result.get('reason', '')})")
                continue
            ok += 1
            detail = ", ".join(result.get("changed") or []) or ("dry-run" if options["dry_run"] else "updated")
            self.stdout.write(f"{spot.name}: {detail}")
        self.stdout.write(self.style.SUCCESS(f"done ok={ok} skipped={skipped} failed={failed}"))
