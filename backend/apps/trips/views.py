from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import timedelta
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.users.permissions import IsPortfolioUser
from rest_framework.views import APIView

from apps.spots.models import WaterSpot
from services.recommendation import (
    ItineraryInfeasibleError,
    ItineraryPlanner,
    ItineraryRequest,
    PartyRequirements,
    ParticipantSkillLevel,
    PreferenceTarget,
    PreferenceVector,
    RecommendationRequest,
)
from services.recommendation.catalog import (
    MAX_CONDITION_AGE,
    DatabaseRecommendationService,
)
from services.public_urls import public_https_url
from services.routing import DatabaseTravelTimeProvider
from services.water_index import SAFETY_MAX_AGE_SECONDS

from .models import Itinerary
from .serializers import (
    ItineraryPlanInputSerializer,
    RecommendationInputSerializer,
    SavedItinerarySerializer,
)
from .throttles import (
    AccountMutationUserRateThrottle,
    RecommendationAnonRateThrottle,
    RecommendationUserRateThrottle,
    RemoteAddressAnonRateThrottle,
)


MAX_CANDIDATE_POOL = 100


class RecommendationView(APIView):
    """Return deterministic, fail-closed recommendations without saving PII."""

    permission_classes = (AllowAny,)
    throttle_classes = (
        RemoteAddressAnonRateThrottle,
        RecommendationAnonRateThrottle,
        RecommendationUserRateThrottle,
    )

    def post(self, request):
        serializer = RecommendationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        queryset = _candidate_queryset(payload)
        candidate_count = queryset.count()
        if not payload.get("region") and candidate_count > MAX_CANDIDATE_POOL:
            return Response(
                {
                    "region": [
                        "Region is required when the candidate pool exceeds "
                        f"{MAX_CANDIDATE_POOL} places."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        spots = tuple(queryset[:MAX_CANDIDATE_POOL])

        try:
            domain_request = _domain_request(payload)
            result = DatabaseRecommendationService().recommend(
                spots=spots,
                activity=payload["activity"],
                request=domain_request,
                limit=payload["limit"],
                at=timezone.now(),
            )
        except (TypeError, ValueError) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        excluded = Counter(
            reason
            for assessment in result.assessments
            if not assessment.eligible
            for reason in (assessment.gate_reasons or assessment.reason_codes)
        )
        recommendations = [
            _serialize_ranked(
                item,
                result=result,
                domain_request=domain_request,
            )
            for item in result.ranked
        ]
        participant_skill_level = (
            domain_request.party.participant_skill_level.value
            if payload["activity"] in {"swim", "surf"}
            else ParticipantSkillLevel.UNSPECIFIED.value
        )
        return Response(
            {
                "generated_at": result.evaluated_at,
                "activity": result.activity,
                "participant_profile": result.participant_profile,
                "participant_skill_level": participant_skill_level,
                "persona_label": domain_request.persona_label,
                "candidate_count": candidate_count,
                "candidate_pool_evaluated": len(spots),
                "candidate_pool_truncated": candidate_count > len(spots),
                "recommendations": recommendations,
                "excluded_summary": dict(sorted(excluded.items())),
                "method": "hard-gates_weighted-fit_mmr-v1",
                "limitations": [
                    "UNKNOWN safety, operation, and requested party constraints are excluded.",
                    "Persona labels are display-only; continuous preferences drive matching.",
                    "Critical safety evidence is revalidated at request time using its metric-specific expiry.",
                    "Family supervision is accepted only as explicit, non-persisted session context.",
                    "Surf suitability requires an explicit skill level that matches the official KHOA grade detail.",
                    "Results use only profile-matched fused Water Index evaluations from the last 15 minutes.",
                ],
            }
        )


class ItineraryPlanView(APIView):
    """Build a deterministic draft using only current persisted route evidence."""

    permission_classes = (AllowAny,)
    throttle_classes = (
        RemoteAddressAnonRateThrottle,
        RecommendationAnonRateThrottle,
        RecommendationUserRateThrottle,
    )

    def post(self, request):
        serializer = ItineraryPlanInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        if payload["save"] and not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication is required to save an itinerary."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        recommendation_payload = payload["recommendation"]
        queryset = _candidate_queryset(recommendation_payload).exclude(
            pk__in=(payload["start_spot"].pk, payload["end_spot"].pk)
        )
        if candidate_ids := payload.get("candidate_ids"):
            queryset = queryset.filter(pk__in=candidate_ids)
        candidate_count = queryset.count()
        if (
            not recommendation_payload.get("region")
            and candidate_count > MAX_CANDIDATE_POOL
        ):
            return Response(
                {
                    "recommendation": {
                        "region": [
                            "Region is required when the candidate pool exceeds "
                            f"{MAX_CANDIDATE_POOL} places."
                        ]
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        spots = tuple(queryset[:12])
        at = timezone.now()

        try:
            domain_request = _domain_request(recommendation_payload)
            recommendation_result = DatabaseRecommendationService().recommend(
                spots=spots,
                activity=recommendation_payload["activity"],
                request=domain_request,
                limit=min(12, max(1, len(spots))),
                at=at,
            )
            route_spot_ids = {
                payload["start_spot"].pk,
                payload["end_spot"].pk,
                *(spot.pk for spot in spots),
            }
            travel_times = DatabaseTravelTimeProvider.current(
                spot_ids=route_spot_ids,
                transport=payload["transport"],
                at=at,
            )
            plan = ItineraryPlanner().plan(
                recommendation_result.assessments,
                ItineraryRequest(
                    start_location_id=str(payload["start_spot"].pk),
                    end_location_id=str(payload["end_spot"].pk),
                    start_minute=payload["start_minute"],
                    end_minute=payload["end_minute"],
                    budget_minor=payload["budget_krw"],
                    bad_weather=payload["bad_weather"],
                ),
                travel_times,
            )
        except ItineraryInfeasibleError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "reason_code": "NO_CURRENT_ROUTE_TO_END",
                    "route_evidence": _serialize_route_evidence(
                        travel_times.evidence
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )
        except (TypeError, ValueError) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan_payload = {
            "visits": [asdict(item) for item in plan.visits],
            "skipped": [asdict(item) for item in plan.skipped],
            "total_cost_krw": plan.total_cost_minor,
            "total_travel_minutes": plan.total_travel_minutes,
            "total_wait_minutes": plan.total_wait_minutes,
            "total_activity_minutes": plan.total_activity_minutes,
            "total_reward": plan.total_reward,
            "end_arrival_minute": plan.end_arrival_minute,
            "method": plan.method,
            "limitations": list(plan.limitations),
        }
        participant_skill_level = (
            domain_request.party.participant_skill_level.value
            if recommendation_payload["activity"] in {"swim", "surf"}
            else ParticipantSkillLevel.UNSPECIFIED.value
        )
        route_evidence = _serialize_route_evidence(travel_times.evidence)
        water_evidence = _serialize_itinerary_water_evidence(
            recommendation_result,
            visited_ids={str(item.candidate_id) for item in plan.visits},
            participant_skill_level=participant_skill_level,
        )
        water_revalidation_at = min(
            (
                row["valid_until"]
                for row in water_evidence
                if row["valid_until"] is not None
            ),
            default=recommendation_result.evaluated_at,
        )
        execution_notice = (
            "This is a logistics draft. Safety, access, operation, weather, "
            "and route evidence must be revalidated before departure and each visit."
        )
        response_payload = {
            "generated_at": at,
            "status": "draft",
            "activity": recommendation_result.activity,
            "participant_profile": recommendation_result.participant_profile,
            "participant_skill_level": participant_skill_level,
            "plan_date": payload["plan_date"],
            "start_spot": _spot_reference(payload["start_spot"]),
            "end_spot": _spot_reference(payload["end_spot"]),
            "transport": payload["transport"],
            "plan": plan_payload,
            "route_evidence": route_evidence,
            "water_evidence": water_evidence,
            "safety_revalidation_required_at": water_revalidation_at,
            "execution_notice": execution_notice,
            "saved_itinerary_id": None,
        }

        if payload["save"]:
            saved = Itinerary.objects.create(
                user=request.user,
                title=payload["title"],
                start_point=payload["start_spot"].name,
                start_spot=payload["start_spot"],
                end_spot=payload["end_spot"],
                transport=payload["transport"],
                is_day_trip=True,
                party_size=len(recommendation_payload["party"]["ages"]),
                budget=payload["budget_krw"],
                activity=recommendation_payload["activity"],
                participant_profile=recommendation_result.participant_profile,
                participant_skill_level=participant_skill_level,
                plan_date=payload["plan_date"],
                start_minute=payload["start_minute"],
                end_minute=payload["end_minute"],
                request_snapshot=_non_sensitive_request_snapshot(
                    payload,
                    participant_profile=(
                        recommendation_result.participant_profile
                    ),
                    participant_skill_level=participant_skill_level,
                ),
                schedule=plan_payload,
                policy_version=(
                    "hard-gates_weighted-fit_mmr-v1+"
                    f"{plan.method}"
                ),
                route_snapshot_ids=list(travel_times.evidence.snapshot_ids),
                route_evidence=_json_safe(route_evidence),
                water_evidence=_json_safe(water_evidence),
                route_revalidation_required_at=travel_times.evidence.valid_until,
                safety_revalidation_required_at=water_revalidation_at,
                execution_notice=execution_notice,
            )
            response_payload["saved_itinerary_id"] = saved.pk

        return Response(response_payload)


class SavedItineraryListView(generics.ListAPIView):
    permission_classes = (IsPortfolioUser,)
    serializer_class = SavedItinerarySerializer

    def get_queryset(self):
        return (
            Itinerary.objects.filter(user=self.request.user)
            .select_related("start_spot", "end_spot")
            .order_by("-updated_at", "-id")
        )


class SavedItineraryDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsPortfolioUser,)
    serializer_class = SavedItinerarySerializer
    http_method_names = ("get", "patch", "delete", "head", "options")

    def get_throttles(self):
        if self.request.method in {"PATCH", "DELETE"}:
            return [AccountMutationUserRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        return Itinerary.objects.filter(user=self.request.user).select_related(
            "start_spot", "end_spot"
        )


def _serialize_ranked(item, *, result, domain_request):
    assessment = item.assessment
    evidence = result.evidence_for(assessment.candidate.spot_id)
    spot = evidence.spot
    condition = evidence.condition_score
    evaluation = evidence.current_evaluation
    sources = []
    source_refs = []
    valid_until = None
    if condition is not None and condition.snapshot is not None:
        metrics = tuple(condition.snapshot.metrics.all())
        sources = sorted({metric.source for metric in metrics})
        source_refs = [_serialize_metric_reference(metric) for metric in metrics]
        expiries = [
            item
            for item in (
                condition.snapshot.valid_until,
                condition.evaluated_at + MAX_CONDITION_AGE,
                *(_metric_valid_until(metric) for metric in metrics),
            )
            if item is not None
        ]
        valid_until = min(expiries, default=None)
    if evidence.session_context_used:
        sources = sorted({*sources, "SESSION_CONTEXT"})
        source_refs.append(
            {
                "metric": "adult_supervision_status",
                "source": "SESSION_CONTEXT",
                "source_url": "",
                "state": "valid",
                "mode": "session_attestation",
                "spatial_scope": f"recommendation-request:spot:{spot.pk}",
                "observed_at": result.evaluated_at,
                "fetched_at": result.evaluated_at,
                "valid_until": result.evaluated_at,
                "persisted": False,
            }
        )
        valid_until = min(
            (item for item in (valid_until, result.evaluated_at) if item is not None),
            default=result.evaluated_at,
        )
    constraints_applied = ["SAFETY_CLEAR", "OPERATION_OPEN", "AGE_POLICY_MATCHED"]
    if domain_request.party.requires_accessibility:
        constraints_applied.append("ACCESSIBILITY_REQUIRED")
    if domain_request.party.bringing_pet:
        constraints_applied.append("PET_ALLOWED_REQUIRED")
    tradeoffs = []
    if assessment.uncertainty_penalty > 0:
        tradeoffs.append("EVIDENCE_UNCERTAINTY_PENALTY")
    if assessment.preference_coverage < 1:
        tradeoffs.append("PREFERENCE_EVIDENCE_PARTIAL")
    if item.mmr_score < (assessment.score or 0):
        tradeoffs.append("DIVERSITY_RERANKING_APPLIED")
    return {
        "rank": item.rank,
        "score": assessment.score,
        "mmr_score": item.mmr_score,
        "spot": {
            "id": spot.pk,
            "name": spot.name,
            "type": spot.type,
            "region": spot.region,
            "address": spot.address,
            "lat": spot.lat,
            "lng": spot.lng,
            "image_url": public_https_url(spot.image_url),
            "tags": spot.tags if isinstance(spot.tags, list) else [],
        },
        "water_index": {
            "participant_profile": (
                condition.participant_profile if condition else None
            ),
            "safety_status": (
                evaluation.safety_status.value if evaluation else "unknown"
            ),
            "suitability_score": evaluation.score if evaluation else None,
            "decision": evaluation.decision.value if evaluation else "unknown",
            "confidence": evaluation.confidence if evaluation else 0.0,
            "methodology_version": (
                evaluation.methodology_version if evaluation else None
            ),
            "evaluated_at": evaluation.evaluated_at if evaluation else None,
            "valid_until": valid_until,
            "sources": sources,
            "source_refs": source_refs,
        },
        "reason_codes": assessment.reason_codes,
        "contributions": [
            {
                "feature": contribution.feature,
                "reason_code": contribution.reason_code,
                "target": contribution.target,
                "candidate_value": contribution.candidate_value,
                "similarity": contribution.similarity,
                "configured_weight": contribution.configured_weight,
                "weighted_points": contribution.weighted_points,
            }
            for contribution in assessment.contributions
        ],
        "evidence_confidence": assessment.effective_confidence,
        "explanation": {
            "policy_version": "recommendation-v1",
            "eligibility": "eligible",
            "positive_reasons": list(assessment.reason_codes),
            "constraints_applied": constraints_applied,
            "tradeoffs": tradeoffs,
            "source_refs": source_refs,
            "freshness": {
                "evaluated_at": evaluation.evaluated_at if evaluation else None,
                "valid_until": valid_until,
            },
            "alternative_ids": [
                ranked.assessment.candidate.spot_id
                for ranked in result.ranked
                if ranked.assessment.candidate.spot_id
                != assessment.candidate.spot_id
            ],
            "adjustable_inputs": ["activity", "region", "preferences"],
        },
    }


def _candidate_queryset(payload):
    queryset = WaterSpot.objects.filter(
        catalog_verification=WaterSpot.VerificationState.VERIFIED,
    ).exclude(catalog_source="PONGDANG_DEMO")
    if region := payload.get("region"):
        queryset = queryset.filter(region__icontains=region.strip())
    if spot_type := payload.get("spot_type"):
        queryset = queryset.filter(type=spot_type)
    return queryset.order_by("pk")


def _domain_request(payload):
    return RecommendationRequest(
        preferences=PreferenceVector(
            tuple(
                PreferenceTarget(
                    item["feature"],
                    item["target"],
                    item["weight"],
                )
                for item in payload["preferences"]
            )
        ),
        party=PartyRequirements(
            ages=tuple(payload["party"]["ages"]),
            requires_accessibility=payload["party"]["requires_accessibility"],
            bringing_pet=payload["party"]["bringing_pet"],
            adult_supervision_confirmed=payload["party"][
                "adult_supervision_confirmed"
            ],
            participant_skill_level=ParticipantSkillLevel(
                payload["party"]["participant_skill_level"]
            ),
        ),
        persona_label=payload["persona_label"],
    )


def _metric_valid_until(metric):
    expiries = []
    if metric.valid_until is not None:
        expiries.append(metric.valid_until)
    if metric.name in SAFETY_MAX_AGE_SECONDS:
        max_age = SAFETY_MAX_AGE_SECONDS[metric.name]
        if max_age is not None:
            expiries.append(metric.observed_at + timedelta(seconds=max_age))
    return min(expiries) if expiries else None


def _serialize_metric_reference(metric):
    return {
        "metric": metric.name,
        "source": metric.source,
        "source_url": public_https_url(metric.source_url),
        "state": metric.state,
        "mode": metric.mode,
        "spatial_scope": metric.spatial_scope,
        "observed_at": metric.observed_at,
        "fetched_at": metric.fetched_at,
        "valid_until": _metric_valid_until(metric),
        "persisted": True,
    }


def _serialize_route_evidence(evidence):
    return {
        "snapshot_ids": list(evidence.snapshot_ids),
        "providers": list(evidence.providers),
        "valid_until": evidence.valid_until,
        "source_urls": [
            url for raw in evidence.source_urls if (url := public_https_url(raw))
        ],
        "available_pairs": evidence.available_pairs,
        "data_state": "live" if evidence.snapshot_ids else "missing",
    }


def _serialize_itinerary_water_evidence(
    result,
    *,
    visited_ids,
    participant_skill_level,
):
    rows = []
    for evidence in result.evidence:
        if str(evidence.spot.pk) not in visited_ids:
            continue
        condition = evidence.condition_score
        evaluation = evidence.current_evaluation
        snapshot = condition.snapshot if condition is not None else None
        metrics = tuple(snapshot.metrics.all()) if snapshot is not None else ()
        expiries = [
            item
            for item in (
                snapshot.valid_until if snapshot is not None else None,
                (
                    condition.evaluated_at + MAX_CONDITION_AGE
                    if condition is not None
                    else None
                ),
                *(_metric_valid_until(metric) for metric in metrics),
            )
            if item is not None
        ]
        if evidence.session_context_used:
            # Adult supervision is a request-scoped attestation and is never
            # persisted as global safety evidence. A saved draft must ask for
            # it again before any execution-state transition.
            expiries.append(result.evaluated_at)
        valid_until = min(expiries, default=None)
        rows.append(
            {
                "spot_id": evidence.spot.pk,
                "condition_score_id": condition.pk if condition is not None else None,
                "snapshot_id": snapshot.pk if snapshot is not None else None,
                "participant_profile": result.participant_profile,
                "participant_skill_level": participant_skill_level,
                "condition_score_participant_skill_level": (
                    getattr(condition, "participant_skill_level", "unspecified")
                    if condition is not None
                    else None
                ),
                "safety_status": (
                    evaluation.safety_status.value if evaluation else "unknown"
                ),
                "decision": evaluation.decision.value if evaluation else "unknown",
                "suitability_score": evaluation.score if evaluation else None,
                "confidence": evaluation.confidence if evaluation else 0.0,
                "methodology_version": (
                    evaluation.methodology_version if evaluation else None
                ),
                "evaluated_at": evaluation.evaluated_at if evaluation else None,
                "valid_until": valid_until,
                "sources": sorted({metric.source for metric in metrics}),
                "source_refs": [
                    _serialize_metric_reference(metric) for metric in metrics
                ],
                "session_context_reconfirmation_required": bool(
                    evidence.session_context_used
                ),
            }
        )
    return rows


def _json_safe(value):
    """Normalize datetimes for immutable JSON audit fields."""

    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _spot_reference(spot):
    return {
        "id": spot.pk,
        "name": spot.name,
        "type": spot.type,
        "region": spot.region,
    }


def _non_sensitive_request_snapshot(
    payload,
    *,
    participant_profile,
    participant_skill_level,
):
    recommendation = payload["recommendation"]
    return {
        "activity": recommendation["activity"],
        "participant_profile": participant_profile,
        "participant_skill_level": participant_skill_level,
        "region": recommendation.get("region", ""),
        "spot_type": recommendation.get("spot_type"),
        "candidate_ids": list(payload.get("candidate_ids", ())),
        "transport": payload["transport"],
        "plan_date": payload["plan_date"].isoformat(),
        "start_minute": payload["start_minute"],
        "end_minute": payload["end_minute"],
        "budget_krw": payload["budget_krw"],
        "bad_weather": payload["bad_weather"],
    }
