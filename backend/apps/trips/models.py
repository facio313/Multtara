from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class TransportMode(models.TextChoices):
    DRIVE = "drive", "Drive"
    WALK = "walk", "Walk"
    BICYCLE = "bicycle", "Bicycle"


class RouteMatrixSnapshot(models.Model):
    """One immutable, expiring response from a routing provider."""

    class Provider(models.TextChoices):
        VALHALLA = "valhalla", "Valhalla"
        OPERATOR = "operator", "Operator-imported"

    class State(models.TextChoices):
        LIVE = "live", "Live"
        ERROR = "error", "Error"

    provider = models.CharField(max_length=20, choices=Provider.choices)
    transport = models.CharField(max_length=16, choices=TransportMode.choices)
    provider_record_id = models.CharField(max_length=128)
    state = models.CharField(max_length=12, choices=State.choices, default=State.LIVE)
    observed_at = models.DateTimeField()
    fetched_at = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField()
    source_url = models.URLField(max_length=500)
    spot_set_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-observed_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "provider_record_id"),
                name="route_snapshot_provider_record_uniq",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__gte=F("observed_at")),
                name="route_snapshot_valid_window",
            ),
            models.CheckConstraint(
                condition=Q(observed_at__lte=F("fetched_at")),
                name="route_snapshot_observed_before_fetch",
            ),
        ]
        indexes = [
            models.Index(
                fields=("transport", "state", "-observed_at"),
                name="route_snap_mode_state_idx",
            ),
        ]


class RouteMatrixEntry(models.Model):
    snapshot = models.ForeignKey(
        RouteMatrixSnapshot,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    origin_spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="route_origins",
    )
    destination_spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="route_destinations",
    )
    duration_seconds = models.PositiveIntegerField()
    distance_metres = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("origin_spot_id", "destination_spot_id")
        constraints = [
            models.UniqueConstraint(
                fields=("snapshot", "origin_spot", "destination_spot"),
                name="route_entry_snapshot_pair_uniq",
            ),
            models.CheckConstraint(
                condition=~Q(origin_spot=F("destination_spot")),
                name="route_entry_distinct_spots",
            ),
            models.CheckConstraint(
                condition=Q(duration_seconds__gte=1),
                name="route_entry_duration_positive",
            ),
            models.CheckConstraint(
                condition=Q(distance_metres__isnull=True)
                | Q(distance_metres__gte=0),
                name="route_entry_distance_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=("origin_spot", "destination_spot"),
                name="route_entry_pair_idx",
            ),
        ]


class Itinerary(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACCEPTED = "accepted", "Accepted"
        STARTED = "started", "Started"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class ParticipantSkillLevel(models.TextChoices):
        UNSPECIFIED = "unspecified", "Unspecified"
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    class ParticipantProfile(models.TextChoices):
        GENERAL = "general", "General"
        FAMILY = "family", "Family"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="itineraries",
    )
    title = models.CharField(max_length=120, blank=True)
    start_point = models.CharField(max_length=200)
    start_spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="itineraries_starting_here",
    )
    end_spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="itineraries_ending_here",
    )
    transport = models.CharField(
        # Retain the legacy storage width so an existing operator label is not
        # truncated by migration. New API writes use TransportMode choices.
        max_length=100,
        choices=TransportMode.choices,
        default=TransportMode.DRIVE,
    )
    is_day_trip = models.BooleanField(default=True)
    party_size = models.PositiveSmallIntegerField(default=1)
    budget = models.PositiveIntegerField(null=True, blank=True)
    activity = models.CharField(max_length=20, blank=True)
    participant_profile = models.CharField(
        max_length=16,
        choices=ParticipantProfile.choices,
        default=ParticipantProfile.GENERAL,
    )
    participant_skill_level = models.CharField(
        max_length=16,
        choices=ParticipantSkillLevel.choices,
        default=ParticipantSkillLevel.UNSPECIFIED,
    )
    plan_date = models.DateField(default=timezone.localdate)
    start_minute = models.PositiveSmallIntegerField(default=0)
    end_minute = models.PositiveSmallIntegerField(default=1_440)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    request_snapshot = models.JSONField(default=dict, blank=True)
    schedule = models.JSONField(default=list, blank=True)
    policy_version = models.CharField(max_length=100, blank=True)
    route_snapshot_ids = models.JSONField(default=list, blank=True)
    route_evidence = models.JSONField(default=dict, blank=True)
    water_evidence = models.JSONField(default=list, blank=True)
    route_revalidation_required_at = models.DateTimeField(null=True, blank=True)
    safety_revalidation_required_at = models.DateTimeField(null=True, blank=True)
    execution_notice = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(party_size__gte=1, party_size__lte=12),
                name="itinerary_party_size_range",
            ),
            models.CheckConstraint(
                condition=Q(start_minute__gte=0)
                & Q(start_minute__lt=F("end_minute"))
                & Q(end_minute__lte=1_440),
                name="itinerary_time_window",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        activity__in=("swim", "surf"),
                        participant_skill_level__in=(
                            "unspecified",
                            "beginner",
                            "intermediate",
                            "advanced",
                        ),
                    )
                    | (
                        ~Q(activity__in=("swim", "surf"))
                        & Q(participant_skill_level="unspecified")
                    )
                ),
                name="itinerary_skill_activity_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        activity="swim",
                        participant_profile__in=("general", "family"),
                    )
                    | (
                        ~Q(activity="swim")
                        & Q(participant_profile="general")
                    )
                ),
                name="itin_profile_activity_valid",
            ),
        ]

    def evidence_revalidation_reasons(
        self,
        *,
        at=None,
        adult_supervision_confirmed: bool = False,
    ) -> tuple[str, ...]:
        """Return bounded reasons why a stored logistics draft is not executable."""

        at = at or timezone.now()
        reasons: list[str] = []
        supervision_required = self.requires_adult_supervision_reconfirmation()
        if (
            self.safety_revalidation_required_at is None
            or self.safety_revalidation_required_at < at
        ) and not (supervision_required and adult_supervision_confirmed is True):
            reasons.append("SAFETY_EVIDENCE_REVALIDATION_REQUIRED")
        if supervision_required and adult_supervision_confirmed is not True:
            reasons.append("ADULT_SUPERVISION_RECONFIRMATION_REQUIRED")
        if (
            self.route_revalidation_required_at is None
            or self.route_revalidation_required_at < at
        ):
            reasons.append("ROUTE_EVIDENCE_REVALIDATION_REQUIRED")
        route_snapshot_ids = (
            self.route_evidence.get("snapshot_ids", [])
            if isinstance(self.route_evidence, dict)
            else []
        )
        if (
            not isinstance(self.route_evidence, dict)
            or self.route_evidence.get("data_state") != "live"
            or not isinstance(route_snapshot_ids, list)
            or not route_snapshot_ids
            or any(
                not isinstance(item, int) or isinstance(item, bool) or item < 1
                for item in route_snapshot_ids
            )
        ):
            reasons.append("ROUTE_EVIDENCE_MISSING")
        elif not self._route_evidence_references_are_current(
            route_snapshot_ids,
            at=at,
        ):
            reasons.append("ROUTE_EVIDENCE_REFERENCE_INVALID")
        visits = self.schedule.get("visits", []) if isinstance(self.schedule, dict) else []
        if visits:
            visit_ids = {
                str(item.get("candidate_id"))
                for item in visits
                if isinstance(item, dict) and item.get("candidate_id") is not None
            }
            water_rows = self.water_evidence if isinstance(self.water_evidence, list) else []
            water_ids = {
                str(item.get("spot_id"))
                for item in water_rows
                if isinstance(item, dict) and item.get("spot_id") is not None
            }
            if not water_rows or not visit_ids or not visit_ids.issubset(water_ids):
                reasons.append("WATER_EVIDENCE_MISSING")
            elif any(not isinstance(item, dict) for item in water_rows) or any(
                not isinstance(item.get("spot_id"), int)
                or isinstance(item.get("spot_id"), bool)
                or item.get("spot_id", 0) < 1
                or item.get("safety_status") != "clear"
                or not isinstance(item.get("condition_score_id"), int)
                or isinstance(item.get("condition_score_id"), bool)
                or item.get("condition_score_id", 0) < 1
                or not isinstance(item.get("snapshot_id"), int)
                or isinstance(item.get("snapshot_id"), bool)
                or item.get("snapshot_id", 0) < 1
                for item in water_rows
                if str(item.get("spot_id")) in visit_ids
            ):
                reasons.append("WATER_EVIDENCE_INVALID")
            elif self.activity in {"swim", "surf"} and (
                (
                    self.activity == "surf"
                    and self.participant_skill_level
                    == self.ParticipantSkillLevel.UNSPECIFIED
                )
                or any(
                    item.get("participant_skill_level")
                    != self.participant_skill_level
                    for item in water_rows
                    if str(item.get("spot_id")) in visit_ids
                )
            ):
                reasons.append("WATER_EVIDENCE_SKILL_MISMATCH")
            elif not self._water_evidence_references_are_current(
                water_rows,
                visit_ids=visit_ids,
                at=at,
            ):
                reasons.append("WATER_EVIDENCE_REFERENCE_INVALID")
        return tuple(dict.fromkeys(reasons))

    def requires_adult_supervision_reconfirmation(self) -> bool:
        if self.activity != "swim" or self.participant_profile != "family":
            return False
        if not isinstance(self.water_evidence, list):
            return False
        return any(
            isinstance(item, dict)
            and item.get("session_context_reconfirmation_required") is True
            for item in self.water_evidence
        )

    def _route_evidence_references_are_current(self, snapshot_ids, *, at) -> bool:
        if (
            not isinstance(self.route_snapshot_ids, list)
            or any(
                not isinstance(item, int) or isinstance(item, bool) or item < 1
                for item in self.route_snapshot_ids
            )
            or len(set(self.route_snapshot_ids)) != len(self.route_snapshot_ids)
            or len(set(snapshot_ids)) != len(snapshot_ids)
            or set(self.route_snapshot_ids) != set(snapshot_ids)
        ):
            return False
        snapshots = tuple(
            RouteMatrixSnapshot.objects.filter(pk__in=set(snapshot_ids))
        )
        return len(snapshots) == len(set(snapshot_ids)) and all(
            item.state == RouteMatrixSnapshot.State.LIVE
            and item.transport == self.transport
            and item.observed_at <= at
            and item.fetched_at <= at
            and item.valid_until >= at
            for item in snapshots
        )

    def _water_evidence_references_are_current(
        self,
        water_rows,
        *,
        visit_ids,
        at,
    ) -> bool:
        from apps.conditions.models import ConditionScore
        from services.water_index import METHODOLOGY_VERSION, SAFETY_MAX_AGE_SECONDS

        relevant = tuple(
            item
            for item in water_rows
            if isinstance(item, dict) and str(item.get("spot_id")) in visit_ids
        )
        score_ids = {item["condition_score_id"] for item in relevant}
        scores = {
            item.pk: item
            for item in ConditionScore.objects.filter(pk__in=score_ids)
            .select_related("snapshot")
            .prefetch_related("snapshot__metrics")
        }
        if len(scores) != len(score_ids):
            return False
        max_age_start = at - timedelta(minutes=15)
        latest_by_identity: dict[tuple[int, str, str], ConditionScore] = {}
        for candidate in ConditionScore.objects.filter(
            spot_id__in={item.get("spot_id") for item in relevant},
            activity=self.activity,
            participant_profile=self.participant_profile,
            methodology_version__in={
                str(item.get("methodology_version")) for item in relevant
            },
            evaluated_at__gte=max_age_start,
            evaluated_at__lte=at,
            snapshot__state="live",
        ).order_by(
            "spot_id",
            "methodology_version",
            "participant_skill_level",
            "-evaluated_at",
            "-id",
        ):
            latest_by_identity.setdefault(
                (
                    candidate.spot_id,
                    candidate.methodology_version,
                    candidate.participant_skill_level,
                ),
                candidate,
            )
        for row in relevant:
            score = scores.get(row["condition_score_id"])
            snapshot = score.snapshot if score is not None else None
            if score is None or snapshot is None:
                return False
            condition_skill = row.get(
                "condition_score_participant_skill_level",
                "unspecified",
            )
            if (
                score.spot_id != row.get("spot_id")
                or score.snapshot_id != row.get("snapshot_id")
                or snapshot.spot_id != row.get("spot_id")
                or score.activity != self.activity
                or score.participant_profile != row.get("participant_profile")
                or score.participant_profile != self.participant_profile
                or row.get("participant_skill_level")
                != self.participant_skill_level
                or score.participant_skill_level != condition_skill
                or score.methodology_version != row.get("methodology_version")
                or score.methodology_version != METHODOLOGY_VERSION
                or snapshot.state != snapshot.SourceState.LIVE
                or score.evaluated_at < max_age_start
                or score.evaluated_at > at
                or snapshot.fetched_at > at
                or (snapshot.valid_from is not None and snapshot.valid_from > at)
                or (snapshot.valid_until is not None and snapshot.valid_until < at)
            ):
                return False
            for metric in snapshot.metrics.all():
                expiries = []
                if metric.valid_until is not None:
                    expiries.append(metric.valid_until)
                max_age = SAFETY_MAX_AGE_SECONDS.get(metric.name)
                if max_age is not None:
                    expiries.append(
                        metric.observed_at + timedelta(seconds=max_age)
                    )
                if (
                    metric.fetched_at > at
                    or (metric.valid_from is not None and metric.valid_from > at)
                    or (expiries and min(expiries) < at)
                ):
                    return False

            desired_skill = (
                self.participant_skill_level
                if self.activity == "surf"
                else self.ParticipantSkillLevel.UNSPECIFIED
            )
            latest = latest_by_identity.get(
                (
                    score.spot_id,
                    score.methodology_version,
                    desired_skill,
                )
            )
            if latest is None or latest.pk != score.pk:
                return False
        return True


class SafetyCard(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="safety_cards",
    )
    spot = models.ForeignKey(
        "spots.WaterSpot",
        on_delete=models.CASCADE,
        related_name="safety_cards",
    )
    condition_snapshot = models.JSONField(default=dict, blank=True)
    risk_factors = models.TextField(blank=True)
    nearest_safety_facility = models.CharField(max_length=200, blank=True)
    shared_with = models.CharField(max_length=255, blank=True)
