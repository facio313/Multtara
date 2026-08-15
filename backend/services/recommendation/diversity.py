"""Deterministic maximal-marginal-relevance ranking."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .domain import Candidate, CandidateAssessment, RankedRecommendation


@dataclass(frozen=True, slots=True)
class MMRPolicy:
    """Balance relevance and novelty; 1.0 means relevance only."""

    relevance_weight: float = 0.65
    minimum_relevance_score: float = 50.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.relevance_weight):
            raise ValueError("relevance_weight must be finite")
        if not 0.0 <= self.relevance_weight <= 1.0:
            raise ValueError("relevance_weight must be between 0 and 1")
        if not math.isfinite(self.minimum_relevance_score):
            raise ValueError("minimum_relevance_score must be finite")
        if not 0.0 <= self.minimum_relevance_score <= 100.0:
            raise ValueError("minimum_relevance_score must be between 0 and 100")


def jaccard_similarity(left: Candidate, right: Candidate) -> float:
    """Measure content similarity from explicit activity/region/diversity tags."""

    union = left.diversity_tokens | right.diversity_tokens
    if not union:
        return 0.0
    return len(left.diversity_tokens & right.diversity_tokens) / len(union)


class MMRSelector:
    def __init__(self, policy: MMRPolicy | None = None) -> None:
        self._policy = policy or MMRPolicy()

    @property
    def policy(self) -> MMRPolicy:
        return self._policy

    def select(
        self,
        assessments: tuple[CandidateAssessment, ...],
        limit: int,
    ) -> tuple[RankedRecommendation, ...]:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        ids = tuple(item.candidate.spot_id for item in assessments)
        if len(ids) != len(set(ids)):
            raise ValueError("assessment candidate ids must be unique")

        remaining = [
            item
            for item in assessments
            if item.eligible
            and item.score is not None
            and item.score >= self._policy.minimum_relevance_score
        ]
        selected: list[RankedRecommendation] = []

        while remaining and len(selected) < limit:
            scored: list[tuple[float, float, str, CandidateAssessment]] = []
            for assessment in remaining:
                assert assessment.score is not None
                relevance = assessment.score / 100.0
                maximum_similarity = max(
                    (
                        jaccard_similarity(
                            assessment.candidate,
                            chosen.assessment.candidate,
                        )
                        for chosen in selected
                    ),
                    default=0.0,
                )
                mmr_score = (
                    self._policy.relevance_weight * relevance
                    - (1.0 - self._policy.relevance_weight) * maximum_similarity
                )
                scored.append(
                    (mmr_score, relevance, assessment.candidate.spot_id, assessment)
                )

            # Explicit sorting makes ties independent of input collection order.
            mmr_score, _relevance, _spot_id, winner = sorted(
                scored,
                key=lambda item: (-item[0], -item[1], item[2]),
            )[0]
            selected.append(
                RankedRecommendation(
                    rank=len(selected) + 1,
                    assessment=winner,
                    mmr_score=round(mmr_score, 6),
                )
            )
            remaining.remove(winner)

        return tuple(selected)
