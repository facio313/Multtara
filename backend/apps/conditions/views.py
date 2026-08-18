import django_filters
from django.db.models import F, OuterRef, Prefetch, Q, Subquery
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ConditionScore, ObservationMetricLineage, ObservationSnapshot
from .serializers import ConditionScoreSerializer, ObservationSnapshotSerializer


class ObservationSnapshotFilter(django_filters.FilterSet):
    # NumberFilter targets the FK column directly and avoids a lookup query that
    # ModelChoiceFilter would perform for every request.
    spot = django_filters.NumberFilter(field_name="spot_id")

    class Meta:
        model = ObservationSnapshot
        fields = ("spot", "provider", "state")


class ConditionScoreFilter(django_filters.FilterSet):
    spot = django_filters.NumberFilter(field_name="spot_id")

    class Meta:
        model = ConditionScore
        fields = (
            "spot",
            "activity",
            "participant_profile",
            "participant_skill_level",
            "safety_status",
            "decision",
        )


class ObservationSnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        ObservationSnapshot.objects.select_related("spot")
        .prefetch_related(
            Prefetch(
                "metrics__lineage_sources",
                queryset=ObservationMetricLineage.objects.select_related(
                    "source_metric__snapshot"
                ),
            )
        )
        .all()
    )
    serializer_class = ObservationSnapshotSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ObservationSnapshotFilter


class ConditionScoreViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        ConditionScore.objects.select_related("spot", "snapshot", "snapshot__spot")
        .prefetch_related(
            Prefetch(
                "snapshot__metrics__lineage_sources",
                queryset=ObservationMetricLineage.objects.select_related(
                    "source_metric__snapshot"
                ),
            )
        )
        .all()
    )
    serializer_class = ConditionScoreSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ConditionScoreFilter

    @action(detail=False, methods=("get",), url_path="latest")
    def latest(self, request, *args, **kwargs):
        """Return the newest evaluation for each spot/activity/profile tuple."""

        as_of = timezone.now()
        applicable_snapshot = (
            Q(snapshot__isnull=True)
            | Q(snapshot__valid_from__isnull=True)
            | Q(snapshot__valid_from__lte=as_of)
        )
        same_spot_snapshot = (
            Q(snapshot__isnull=True) | Q(snapshot__spot_id=F("spot_id"))
        )
        latest_id = (
            ConditionScore.objects.filter(
                spot_id=OuterRef("spot_id"),
                activity=OuterRef("activity"),
                participant_profile=OuterRef("participant_profile"),
                participant_skill_level=OuterRef("participant_skill_level"),
            )
            .filter(evaluated_at__lte=as_of)
            .filter(applicable_snapshot)
            .filter(same_spot_snapshot)
            .order_by("-evaluated_at", "-id")
            .values("id")[:1]
        )
        base_queryset = self.get_queryset()
        if "participant_profile" not in request.query_params:
            # Preserve the pre-profile API's one-row-per-spot/activity shape.
            # Family consumers must opt in explicitly so an UNKNOWN family
            # evaluation cannot accidentally replace the general display row.
            base_queryset = base_queryset.filter(participant_profile="general")
        if "participant_skill_level" not in request.query_params:
            # Skill-specific surf rows are opt-in. The backwards-compatible
            # default is the explicitly unscoped, fail-closed identity.
            base_queryset = base_queryset.filter(
                participant_skill_level="unspecified"
            )
        queryset = (
            self.filter_queryset(base_queryset)
            .filter(evaluated_at__lte=as_of)
            .filter(applicable_snapshot)
            .filter(same_spot_snapshot)
            .filter(id=Subquery(latest_id))
        )
        serializer_context = {
            **self.get_serializer_context(),
            "effective_as_of": as_of,
        }
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(
                page,
                many=True,
                context=serializer_context,
            )
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(
            queryset,
            many=True,
            context=serializer_context,
        )
        return Response(serializer.data)
