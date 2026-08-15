from __future__ import annotations

from collections import Counter

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.spots.models import WaterSpot
from services.recommendation import (
    PartyRequirements,
    ParticipantSkillLevel,
    PreferenceTarget,
    PreferenceVector,
    RecommendationRequest,
)
from services.recommendation.catalog import DatabaseRecommendationService
from services.public_urls import public_https_url

from .serializers import RecommendationInputSerializer
from .throttles import RecommendationAnonRateThrottle, RemoteAddressAnonRateThrottle


MAX_CANDIDATE_POOL = 100


class RecommendationView(APIView):
    """Return deterministic, fail-closed recommendations without saving PII."""

    permission_classes = (AllowAny,)
    throttle_classes = (
        RemoteAddressAnonRateThrottle,
        RecommendationAnonRateThrottle,
    )

    def post(self, request):
        serializer = RecommendationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        queryset = WaterSpot.objects.all()
        if region := payload.get("region"):
            queryset = queryset.filter(region__iexact=region)
        if spot_type := payload.get("spot_type"):
            queryset = queryset.filter(type=spot_type)
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
            domain_request = RecommendationRequest(
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
                    requires_accessibility=payload["party"][
                        "requires_accessibility"
                    ],
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
            _serialize_ranked(item, result=result) for item in result.ranked
        ]
        return Response(
            {
                "generated_at": result.evaluated_at,
                "activity": result.activity,
                "participant_profile": result.participant_profile,
                "participant_skill_level": (
                    domain_request.party.participant_skill_level.value
                ),
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


def _serialize_ranked(item, *, result):
    assessment = item.assessment
    evidence = result.evidence_for(assessment.candidate.spot_id)
    spot = evidence.spot
    condition = evidence.condition_score
    evaluation = evidence.current_evaluation
    sources = []
    if condition is not None and condition.snapshot is not None:
        sources = sorted({metric.source for metric in condition.snapshot.metrics.all()})
    if evidence.session_context_used:
        sources = sorted({*sources, "SESSION_CONTEXT"})
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
            "sources": sources,
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
    }
