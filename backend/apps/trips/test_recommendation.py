"""Boundary and property-style tests for the pure recommendation engine."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from unittest import TestCase

from services.recommendation import (
    AgePolicy,
    Candidate,
    FeatureValue,
    FeatureVector,
    GateValue,
    ItineraryPlanner,
    ItineraryRequest,
    MMRPolicy,
    MMRSelector,
    PartyRequirements,
    PreferenceTarget,
    PreferenceVector,
    RecommendationEngine,
    RecommendationRequest,
    ScoringPolicy,
    TimeWindow,
    TravelTime,
    TravelTimeMatrix,
)


def candidate(
    spot_id: str,
    *,
    quiet: float = 1.0,
    activity_level: float = 0.0,
    feature_values: tuple[FeatureValue, ...] | None = None,
    safety: GateValue = GateValue.ALLOW,
    operation: GateValue = GateValue.ALLOW,
    accessibility: GateValue = GateValue.ALLOW,
    pet_policy: GateValue = GateValue.ALLOW,
    age_policy: AgePolicy = AgePolicy(known=True),
    evidence_confidence: float = 1.0,
    activity: str = "water-view",
    region: str = "gangneung",
    tags: frozenset[str] = frozenset({"calm", "coast"}),
    windows: tuple[TimeWindow, ...] = (TimeWindow(480, 1_000),),
    duration: int = 30,
    cost: int = 1_000,
    indoor: bool = False,
    bad_weather_suitable: bool = False,
) -> Candidate:
    features = feature_values
    if features is None:
        features = (
            FeatureValue("quiet", quiet),
            FeatureValue("activity_level", activity_level),
        )
    return Candidate(
        spot_id=spot_id,
        name=f"Spot {spot_id}",
        activity=activity,
        region=region,
        features=FeatureVector(features),
        time_windows=windows,
        duration_minutes=duration,
        cost_minor=cost,
        safety=safety,
        operation=operation,
        accessibility=accessibility,
        pet_policy=pet_policy,
        age_policy=age_policy,
        evidence_confidence=evidence_confidence,
        diversity_tags=tags,
        indoor=indoor,
        bad_weather_suitable=bad_weather_suitable,
    )


def request(
    *,
    ages: tuple[int, ...] = (30,),
    accessibility: bool = False,
    pet: bool = False,
    persona: str = "display-only",
) -> RecommendationRequest:
    return RecommendationRequest(
        preferences=PreferenceVector(
            (
                PreferenceTarget("quiet", 1.0, 0.6),
                PreferenceTarget("activity_level", 0.0, 0.4),
            )
        ),
        party=PartyRequirements(
            ages=ages,
            requires_accessibility=accessibility,
            bringing_pet=pet,
        ),
        persona_label=persona,
    )


def matrix_for(
    nodes: tuple[str, ...],
    *,
    minutes: int = 5,
) -> TravelTimeMatrix:
    return TravelTimeMatrix(
        tuple(
            TravelTime(origin, destination, minutes)
            for origin in nodes
            for destination in nodes
            if origin != destination
        )
    )


class HardGateTests(TestCase):
    def test_every_mandatory_gate_fails_closed_with_a_reason(self) -> None:
        base = candidate("base")
        constrained_request = request(ages=(10, 40), accessibility=True, pet=True)
        cases = (
            (replace(base, safety=GateValue.DENY), "SAFETY_BLOCKED"),
            (replace(base, safety=GateValue.UNKNOWN), "SAFETY_UNKNOWN"),
            (replace(base, operation=GateValue.DENY), "OPERATION_CLOSED"),
            (replace(base, operation=GateValue.UNKNOWN), "OPERATION_UNKNOWN"),
            (
                replace(base, accessibility=GateValue.DENY),
                "ACCESSIBILITY_UNAVAILABLE",
            ),
            (
                replace(base, accessibility=GateValue.UNKNOWN),
                "ACCESSIBILITY_UNKNOWN",
            ),
            (replace(base, pet_policy=GateValue.DENY), "PET_NOT_ALLOWED"),
            (replace(base, pet_policy=GateValue.UNKNOWN), "PET_POLICY_UNKNOWN"),
            (replace(base, age_policy=AgePolicy(known=False)), "AGE_POLICY_UNKNOWN"),
            (
                replace(base, age_policy=AgePolicy(known=True, minimum_age=11)),
                "AGE_BELOW_MINIMUM",
            ),
            (
                replace(base, age_policy=AgePolicy(known=True, maximum_age=39)),
                "AGE_ABOVE_MAXIMUM",
            ),
        )
        engine = RecommendationEngine()
        for item, expected_reason in cases:
            with self.subTest(reason=expected_reason):
                assessment = engine.assess(item, constrained_request)
                self.assertFalse(assessment.eligible)
                self.assertIsNone(assessment.score)
                self.assertIn(expected_reason, assessment.gate_reasons)

    def test_optional_accessibility_and_pet_unknown_do_not_gate(self) -> None:
        item = candidate(
            "optional",
            accessibility=GateValue.UNKNOWN,
            pet_policy=GateValue.UNKNOWN,
        )
        self.assertTrue(RecommendationEngine().assess(item, request()).eligible)

    def test_property_unsafe_is_never_ranked_regardless_of_fit_or_confidence(self) -> None:
        engine = RecommendationEngine()
        selector = MMRSelector()
        for safety in (GateValue.DENY, GateValue.UNKNOWN):
            for confidence in (0.0, 0.5, 1.0):
                for quiet in (0.0, 0.5, 1.0):
                    item = candidate(
                        f"unsafe-{safety.value}-{confidence}-{quiet}",
                        safety=safety,
                        quiet=quiet,
                        evidence_confidence=confidence,
                    )
                    assessment = engine.assess(item, request())
                    self.assertFalse(assessment.eligible)
                    self.assertEqual(selector.select((assessment,), 1), ())

    def test_manually_inconsistent_assessment_cannot_launder_safety_gate(self) -> None:
        engine = RecommendationEngine()
        safe = candidate("safe")
        safe_assessment = engine.assess(safe, request())
        inconsistent = replace(
            safe_assessment,
            candidate=replace(safe, safety=GateValue.DENY),
        )
        self.assertFalse(inconsistent.eligible)
        self.assertEqual(MMRSelector().select((inconsistent,), 1), ())


class ScoringTests(TestCase):
    def test_persona_label_is_display_only(self) -> None:
        item = candidate("persona")
        first = RecommendationEngine().assess(item, request(persona="healing"))
        second = RecommendationEngine().assess(item, request(persona="adventure"))
        self.assertEqual(first, second)

    def test_uncertainty_penalty_uses_confidence_and_weighted_coverage(self) -> None:
        engine = RecommendationEngine(ScoringPolicy(uncertainty_penalty_rate=0.35))
        full = engine.assess(candidate("full"), request())
        low_confidence = engine.assess(
            candidate("low", evidence_confidence=0.0),
            request(),
        )
        partial = engine.assess(
            candidate(
                "partial",
                feature_values=(FeatureValue("quiet", 1.0),),
            ),
            request(),
        )

        self.assertEqual(full.base_score, 100.0)
        self.assertEqual(full.score, 100.0)
        self.assertEqual(full.uncertainty_penalty, 0.0)
        self.assertEqual(low_confidence.score, 65.0)
        self.assertIn("UNCERTAINTY_PENALTY", low_confidence.reason_codes)
        self.assertEqual(partial.preference_coverage, 0.6)
        self.assertEqual(partial.effective_confidence, 0.6)
        self.assertEqual(partial.score, 86.0)
        self.assertEqual(
            partial.contributions[0].reason_code,
            "PREFERENCE_MATCH_QUIET",
        )

    def test_missing_all_preference_evidence_is_not_recommendable(self) -> None:
        assessment = RecommendationEngine().assess(
            candidate(
                "missing",
                feature_values=(FeatureValue("social", 0.5),),
            ),
            request(),
        )
        self.assertTrue(assessment.hard_gate_passed)
        self.assertFalse(assessment.eligible)
        self.assertEqual(assessment.reason_codes, ("PREFERENCE_EVIDENCE_MISSING",))

    def test_domain_inputs_are_immutable_and_canonical(self) -> None:
        item = candidate("immutable", tags=frozenset({"  Slow Pace ", "COAST"}))
        self.assertIn("slow_pace", item.diversity_tags)
        with self.assertRaises(FrozenInstanceError):
            item.name = "changed"  # type: ignore[misc]


class DiversityTests(TestCase):
    def test_mmr_never_uses_diversity_to_insert_below_floor_candidate(self) -> None:
        relevant = candidate("relevant", quiet=1.0)
        irrelevant = candidate(
            "irrelevant",
            feature_values=(
                FeatureValue("quiet", 0.0),
                FeatureValue("activity_level", 1.0),
            ),
            activity="hot-spring",
            region="sokcho",
            tags=frozenset({"indoor", "thermal"}),
            indoor=True,
            bad_weather_suitable=True,
        )
        assessed = RecommendationEngine().assess_all(
            (relevant, irrelevant),
            request(),
        )
        selected = MMRSelector(
            MMRPolicy(relevance_weight=0.0, minimum_relevance_score=50.0)
        ).select(assessed, 2)
        self.assertEqual(
            tuple(item.assessment.candidate.spot_id for item in selected),
            ("relevant",),
        )

    def test_mmr_is_deterministic_and_promotes_a_distinct_second_result(self) -> None:
        items = (
            candidate("a", quiet=1.0),
            candidate("b", quiet=0.99),
            candidate(
                "c",
                quiet=0.8,
                activity="hot-spring",
                region="sokcho",
                tags=frozenset({"indoor", "thermal"}),
                indoor=True,
                bad_weather_suitable=True,
            ),
        )
        engine = RecommendationEngine()
        assessed = engine.assess_all(items, request())
        selector = MMRSelector(MMRPolicy(relevance_weight=0.55))

        forward = selector.select(assessed, 3)
        reverse = selector.select(tuple(reversed(assessed)), 3)
        forward_ids = tuple(item.assessment.candidate.spot_id for item in forward)
        reverse_ids = tuple(item.assessment.candidate.spot_id for item in reverse)

        self.assertEqual(forward_ids, ("a", "c", "b"))
        self.assertEqual(reverse_ids, forward_ids)
        self.assertNotEqual(
            forward[0].assessment.candidate.activity,
            forward[1].assessment.candidate.activity,
        )


class ItineraryTests(TestCase):
    def setUp(self) -> None:
        self.engine = RecommendationEngine()
        self.planner = ItineraryPlanner()

    def test_exact_budget_window_and_return_boundaries_are_feasible(self) -> None:
        item = candidate(
            "a",
            windows=(TimeWindow(500, 530),),
            duration=30,
            cost=1_000,
        )
        assessed = self.engine.assess_all((item,), request())
        travel = TravelTimeMatrix(
            (
                TravelTime("origin", "a", 10),
                TravelTime("a", "destination", 20),
                TravelTime("origin", "destination", 5),
            )
        )
        exact = self.planner.plan(
            assessed,
            ItineraryRequest("origin", "destination", 480, 550, 1_000),
            travel,
        )
        self.assertEqual(tuple(visit.candidate_id for visit in exact.visits), ("a",))
        self.assertEqual(exact.visits[0].start_minute, 500)
        self.assertEqual(exact.visits[0].end_minute, 530)
        self.assertEqual(exact.end_arrival_minute, 550)
        self.assertEqual(exact.total_cost_minor, 1_000)

        too_little_money = self.planner.plan(
            assessed,
            ItineraryRequest("origin", "destination", 480, 550, 999),
            travel,
        )
        too_little_time = self.planner.plan(
            assessed,
            ItineraryRequest("origin", "destination", 480, 549, 1_000),
            travel,
        )
        self.assertEqual(too_little_money.visits, ())
        self.assertEqual(too_little_time.visits, ())
        self.assertEqual(too_little_money.skipped[0].reason_code, "BUDGET_EXCEEDED")
        self.assertEqual(too_little_time.skipped[0].reason_code, "RETURN_TIME_INFEASIBLE")

    def test_bad_weather_uses_only_verified_indoor_fallbacks(self) -> None:
        outdoor = candidate("outdoor", quiet=1.0, cost=0)
        indoor = candidate(
            "indoor",
            quiet=0.8,
            activity="hot-spring",
            tags=frozenset({"indoor"}),
            cost=0,
            indoor=True,
            bad_weather_suitable=True,
        )
        assessed = self.engine.assess_all((outdoor, indoor), request())
        travel = matrix_for(("origin", "outdoor", "indoor", "destination"))
        plan = self.planner.plan(
            assessed,
            ItineraryRequest("origin", "destination", 480, 600, 0, bad_weather=True),
            travel,
        )
        self.assertEqual(tuple(visit.candidate_id for visit in plan.visits), ("indoor",))
        self.assertTrue(plan.visits[0].is_bad_weather_fallback)
        reasons = {item.candidate_id: item.reason_code for item in plan.skipped}
        self.assertEqual(
            reasons["outdoor"],
            "BAD_WEATHER_INDOOR_FALLBACK_REQUIRED",
        )

    def test_missing_travel_time_excludes_candidate_without_guessing(self) -> None:
        item = candidate("unroutable", cost=0)
        assessed = self.engine.assess_all((item,), request())
        travel = TravelTimeMatrix((TravelTime("origin", "destination", 5),))
        plan = self.planner.plan(
            assessed,
            ItineraryRequest("origin", "destination", 480, 600, 0),
            travel,
        )
        self.assertEqual(plan.visits, ())
        self.assertEqual(plan.skipped[0].reason_code, "NO_TRAVEL_TIME")

    def test_property_every_generated_plan_respects_all_constraints(self) -> None:
        items = (
            candidate("a", duration=20, cost=300, quiet=1.0),
            candidate("b", duration=25, cost=500, quiet=0.9),
            candidate("c", duration=35, cost=700, quiet=0.8),
            candidate("unsafe", duration=10, cost=0, safety=GateValue.DENY),
        )
        by_id = {item.spot_id: item for item in items}
        assessed = self.engine.assess_all(items, request())
        travel = matrix_for(("origin", "a", "b", "c", "unsafe", "destination"))

        for budget in (0, 299, 300, 799, 1_500):
            for end_minute in (520, 560, 640, 760):
                with self.subTest(budget=budget, end_minute=end_minute):
                    plan_request = ItineraryRequest(
                        "origin",
                        "destination",
                        480,
                        end_minute,
                        budget,
                    )
                    plan = self.planner.plan(assessed, plan_request, travel)
                    self.assertLessEqual(plan.total_cost_minor, budget)
                    self.assertLessEqual(plan.end_arrival_minute, end_minute)
                    self.assertEqual(
                        len(plan.visits),
                        len({visit.candidate_id for visit in plan.visits}),
                    )
                    self.assertNotIn(
                        "unsafe",
                        {visit.candidate_id for visit in plan.visits},
                    )

                    location = "origin"
                    minute = 480
                    summed_cost = 0
                    summed_travel = 0
                    summed_wait = 0
                    summed_activity = 0
                    for visit in plan.visits:
                        selected = by_id[visit.candidate_id]
                        inbound = travel.minutes(location, selected.spot_id)
                        self.assertIsNotNone(inbound)
                        self.assertEqual(visit.arrival_minute, minute + inbound)  # type: ignore[operator]
                        self.assertGreaterEqual(visit.start_minute, visit.arrival_minute)
                        self.assertEqual(
                            visit.end_minute - visit.start_minute,
                            selected.duration_minutes,
                        )
                        self.assertTrue(
                            any(
                                window.start_minute <= visit.start_minute
                                and visit.end_minute <= window.end_minute
                                for window in selected.time_windows
                            )
                        )
                        summed_cost += selected.cost_minor
                        summed_travel += visit.travel_minutes
                        summed_wait += visit.wait_minutes
                        summed_activity += selected.duration_minutes
                        location = selected.spot_id
                        minute = visit.end_minute

                    final_leg = travel.minutes(location, "destination")
                    self.assertIsNotNone(final_leg)
                    self.assertEqual(plan.end_arrival_minute, minute + final_leg)  # type: ignore[operator]
                    self.assertEqual(plan.total_cost_minor, summed_cost)
                    self.assertEqual(plan.total_travel_minutes, summed_travel + final_leg)  # type: ignore[operator]
                    self.assertEqual(plan.total_wait_minutes, summed_wait)
                    self.assertEqual(plan.total_activity_minutes, summed_activity)

    def test_itinerary_is_deterministic_under_input_reordering(self) -> None:
        items = (
            candidate("a", quiet=1.0, cost=0),
            candidate("b", quiet=0.9, cost=0),
            candidate("c", quiet=0.8, cost=0),
        )
        assessed = self.engine.assess_all(items, request())
        travel = matrix_for(("origin", "a", "b", "c", "destination"))
        plan_request = ItineraryRequest("origin", "destination", 480, 640, 0)
        forward = self.planner.plan(assessed, plan_request, travel)
        reverse = self.planner.plan(tuple(reversed(assessed)), plan_request, travel)
        self.assertEqual(forward, reverse)
