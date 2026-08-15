"""Dependency-free deterministic itinerary feasibility and greedy routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Protocol

from .domain import (
    Candidate,
    CandidateAssessment,
    ItineraryPlan,
    ItineraryRequest,
    ScheduledVisit,
    SkippedCandidate,
    TimeWindow,
    TravelTime,
)


class TravelTimeProvider(Protocol):
    """Injected, side-effect-free travel-time lookup contract."""

    def minutes(self, origin_id: str, destination_id: str) -> int | None:
        """Return non-negative minutes, or ``None`` when no route is known."""


@dataclass(frozen=True, slots=True)
class TravelTimeMatrix:
    """Immutable in-memory provider suitable for tests and precomputed routes."""

    entries: tuple[TravelTime, ...]
    _lookup: Mapping[tuple[str, str], int] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        ordered = tuple(
            sorted(self.entries, key=lambda item: (item.origin_id, item.destination_id))
        )
        lookup: dict[tuple[str, str], int] = {}
        for entry in ordered:
            key = (entry.origin_id, entry.destination_id)
            if key in lookup:
                raise ValueError(f"duplicate travel-time entry: {key!r}")
            lookup[key] = entry.minutes
        object.__setattr__(self, "entries", ordered)
        object.__setattr__(self, "_lookup", MappingProxyType(lookup))

    def minutes(self, origin_id: str, destination_id: str) -> int | None:
        if origin_id == destination_id:
            return 0
        return self._lookup.get((origin_id, destination_id))


class ItineraryInfeasibleError(ValueError):
    """Raised when the requested start-to-end journey itself is infeasible."""


@dataclass(frozen=True, slots=True)
class _FeasibleStep:
    assessment: CandidateAssessment
    arrival_minute: int
    start_minute: int
    end_minute: int
    travel_minutes: int
    wait_minutes: int
    return_minutes: int
    density: float


def _earliest_window(
    candidate: Candidate,
    arrival_minute: int,
) -> tuple[TimeWindow, int, int] | None:
    options: list[tuple[int, int, TimeWindow]] = []
    for window in candidate.time_windows:
        start = max(arrival_minute, window.start_minute)
        end = start + candidate.duration_minutes
        if end <= window.end_minute:
            options.append((end, start, window))
    if not options:
        return None
    end, start, window = sorted(
        options,
        key=lambda item: (item[0], item[1], item[2].start_minute),
    )[0]
    return window, start, end


class ItineraryPlanner:
    """Greedy deterministic orienteering baseline with strict feasibility.

    Every proposed step preserves a known return path to the requested end.
    This guarantees feasible prefixes but does not claim a globally optimal
    route (unlike an exact or mixed-integer solver).
    """

    @staticmethod
    def _step(
        assessment: CandidateAssessment,
        *,
        current_location: str,
        current_minute: int,
        current_cost: int,
        request: ItineraryRequest,
        travel_times: TravelTimeProvider,
    ) -> _FeasibleStep | None:
        if not assessment.eligible or assessment.score is None or assessment.score <= 0.0:
            return None
        candidate = assessment.candidate
        if request.bad_weather and not (
            candidate.indoor and candidate.bad_weather_suitable
        ):
            return None
        if current_cost + candidate.cost_minor > request.budget_minor:
            return None
        travel = travel_times.minutes(current_location, candidate.spot_id)
        return_travel = travel_times.minutes(
            candidate.spot_id,
            request.end_location_id,
        )
        if travel is None or return_travel is None or travel < 0 or return_travel < 0:
            return None
        arrival = current_minute + travel
        feasible_window = _earliest_window(candidate, arrival)
        if feasible_window is None:
            return None
        _window, start, end = feasible_window
        if end + return_travel > request.end_minute:
            return None
        wait = start - arrival
        incremental_minutes = travel + wait + candidate.duration_minutes
        density = assessment.score / max(1, incremental_minutes)
        return _FeasibleStep(
            assessment=assessment,
            arrival_minute=arrival,
            start_minute=start,
            end_minute=end,
            travel_minutes=travel,
            wait_minutes=wait,
            return_minutes=return_travel,
            density=density,
        )

    @staticmethod
    def _skip_reason(
        assessment: CandidateAssessment,
        *,
        current_location: str,
        current_minute: int,
        current_cost: int,
        request: ItineraryRequest,
        travel_times: TravelTimeProvider,
    ) -> str:
        if not assessment.hard_gate_passed or (
            assessment.score is not None and not assessment.eligible
        ):
            return "HARD_GATE_FAILED"
        if assessment.score is None:
            return "PREFERENCE_EVIDENCE_MISSING"
        if assessment.score <= 0.0:
            return "NON_POSITIVE_REWARD"
        candidate = assessment.candidate
        if request.bad_weather and not (
            candidate.indoor and candidate.bad_weather_suitable
        ):
            return "BAD_WEATHER_INDOOR_FALLBACK_REQUIRED"
        if current_cost + candidate.cost_minor > request.budget_minor:
            return "BUDGET_EXCEEDED"
        travel = travel_times.minutes(current_location, candidate.spot_id)
        return_travel = travel_times.minutes(
            candidate.spot_id,
            request.end_location_id,
        )
        if travel is None or return_travel is None or travel < 0 or return_travel < 0:
            return "NO_TRAVEL_TIME"
        arrival = current_minute + travel
        feasible_window = _earliest_window(candidate, arrival)
        if feasible_window is None:
            return "TIME_WINDOW_INFEASIBLE"
        _window, _start, end = feasible_window
        if end + return_travel > request.end_minute:
            return "RETURN_TIME_INFEASIBLE"
        return "NOT_SELECTED_BY_GREEDY_OBJECTIVE"

    def plan(
        self,
        assessments: tuple[CandidateAssessment, ...],
        request: ItineraryRequest,
        travel_times: TravelTimeProvider,
    ) -> ItineraryPlan:
        ids = tuple(item.candidate.spot_id for item in assessments)
        if len(ids) != len(set(ids)):
            raise ValueError("assessment candidate ids must be unique")

        remaining = list(assessments)
        visits: list[ScheduledVisit] = []
        current_location = request.start_location_id
        current_minute = request.start_minute
        total_cost = 0
        total_travel = 0
        total_wait = 0
        total_activity = 0
        total_reward = 0.0

        while remaining:
            feasible = [
                step
                for assessment in remaining
                if (
                    step := self._step(
                        assessment,
                        current_location=current_location,
                        current_minute=current_minute,
                        current_cost=total_cost,
                        request=request,
                        travel_times=travel_times,
                    )
                )
                is not None
            ]
            if not feasible:
                break
            chosen = sorted(
                feasible,
                key=lambda step: (
                    -step.density,
                    -(step.assessment.score or 0.0),
                    step.end_minute,
                    step.assessment.candidate.spot_id,
                ),
            )[0]
            candidate = chosen.assessment.candidate
            visits.append(
                ScheduledVisit(
                    candidate_id=candidate.spot_id,
                    candidate_name=candidate.name,
                    arrival_minute=chosen.arrival_minute,
                    start_minute=chosen.start_minute,
                    end_minute=chosen.end_minute,
                    travel_minutes=chosen.travel_minutes,
                    wait_minutes=chosen.wait_minutes,
                    cost_minor=candidate.cost_minor,
                    reward=chosen.assessment.score or 0.0,
                    is_bad_weather_fallback=request.bad_weather
                    and candidate.indoor
                    and candidate.bad_weather_suitable,
                )
            )
            current_location = candidate.spot_id
            current_minute = chosen.end_minute
            total_cost += candidate.cost_minor
            total_travel += chosen.travel_minutes
            total_wait += chosen.wait_minutes
            total_activity += candidate.duration_minutes
            total_reward += chosen.assessment.score or 0.0
            remaining.remove(chosen.assessment)

        final_travel = travel_times.minutes(current_location, request.end_location_id)
        if final_travel is None or final_travel < 0:
            raise ItineraryInfeasibleError(
                "no travel time is available from the final location to the end"
            )
        end_arrival = current_minute + final_travel
        if end_arrival > request.end_minute:
            # Defensive invariant: _step checks this after every accepted visit.
            raise ItineraryInfeasibleError("the route cannot reach the end on time")
        total_travel += final_travel

        skipped = tuple(
            SkippedCandidate(
                candidate_id=assessment.candidate.spot_id,
                reason_code=self._skip_reason(
                    assessment,
                    current_location=current_location,
                    current_minute=current_minute,
                    current_cost=total_cost,
                    request=request,
                    travel_times=travel_times,
                ),
            )
            for assessment in sorted(
                remaining,
                key=lambda item: item.candidate.spot_id,
            )
        )
        return ItineraryPlan(
            visits=tuple(visits),
            skipped=skipped,
            total_cost_minor=total_cost,
            total_travel_minutes=total_travel,
            total_wait_minutes=total_wait,
            total_activity_minutes=total_activity,
            total_reward=round(total_reward, 6),
            end_arrival_minute=end_arrival,
        )
