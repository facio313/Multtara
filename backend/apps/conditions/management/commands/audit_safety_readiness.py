from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.spots.models import WaterSpot
from services.safety_readiness import audit_safety_readiness


class Command(BaseCommand):
    help = (
        "Audit whether curated spots have current evidence-backed Water Index "
        "evaluations; never treats pipeline success as safety clearance."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--spot", action="append", dest="spot_ids", type=int)
        parser.add_argument(
            "--profile",
            action="append",
            choices=("general", "family"),
            dest="profiles",
        )
        parser.add_argument("--json", action="store_true", dest="as_json")
        parser.add_argument(
            "--require-current-clear",
            action="store_true",
            help="Exit non-zero unless at least one audited evaluation is currently CLEAR.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        queryset = WaterSpot.objects.exclude(catalog_source="PONGDANG_DEMO").order_by("pk")
        if options.get("spot_ids"):
            queryset = queryset.filter(pk__in=options["spot_ids"])
        else:
            queryset = queryset.filter(catalog_verification="verified")
        spots = tuple(queryset[:501])
        if not spots:
            raise CommandError("No audited WaterSpot rows match the selection")
        if len(spots) > 500:
            raise CommandError("Safety readiness audit is limited to 500 spots")

        report = audit_safety_readiness(
            at=timezone.now(),
            spots=spots,
            profiles=tuple(options.get("profiles") or ("general", "family")),
        )
        payload = {
            "status": "ok" if report.current_clear_count else "degraded",
            "checked_at": report.checked_at.isoformat(),
            "spots": len(spots),
            "evaluations": len(report.entries),
            "counts": report.counts,
            "entries": [
                {
                    "spot_id": entry.spot_id,
                    "spot_name": entry.spot_name,
                    "activity": entry.activity,
                    "participant_profile": entry.participant_profile,
                    "safety_status": entry.safety_status,
                    "decision": entry.decision,
                    "reason_codes": entry.reason_codes,
                }
                for entry in report.entries
            ],
        }
        if options["as_json"]:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            counts = " ".join(
                f"{status}={count}" for status, count in report.counts.items()
            )
            self.stdout.write(
                f"Safety readiness: spots={len(spots)} "
                f"evaluations={len(report.entries)} {counts}"
            )

        if options["require_current_clear"] and not report.current_clear_count:
            raise CommandError("No audited evaluation has current CLEAR evidence")
