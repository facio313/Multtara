"""Deterministic scoring curves used by Water Index profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .domain import MetricValue


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


@dataclass(frozen=True, slots=True)
class PiecewiseLinear:
    points: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("a piecewise curve needs at least two points")
        xs = [point[0] for point in self.points]
        if xs != sorted(xs) or len(xs) != len(set(xs)):
            raise ValueError("curve x coordinates must be unique and increasing")
        if any(not 0 <= score <= 100 for _, score in self.points):
            raise ValueError("curve scores must be between 0 and 100")

    def __call__(self, value: MetricValue) -> float:
        numeric = float(value)
        if numeric <= self.points[0][0]:
            return self.points[0][1]
        if numeric >= self.points[-1][0]:
            return self.points[-1][1]
        for (left_x, left_y), (right_x, right_y) in zip(self.points, self.points[1:]):
            if left_x <= numeric <= right_x:
                ratio = (numeric - left_x) / (right_x - left_x)
                return clamp_score(left_y + ratio * (right_y - left_y))
        raise AssertionError("piecewise interval lookup failed")


@dataclass(frozen=True, slots=True)
class CategoryScores:
    scores: Mapping[str, float]

    def __call__(self, value: MetricValue) -> float:
        key = str(value).strip().lower().replace(" ", "_")
        if key not in self.scores:
            raise ValueError(f"unsupported category: {value!r}")
        return clamp_score(float(self.scores[key]))


IDENTITY_SCORE = PiecewiseLinear(((0.0, 0.0), (100.0, 100.0)))
