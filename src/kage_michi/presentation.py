"""UI-neutral view models; Streamlit integration belongs in a later issue."""

from __future__ import annotations

from dataclasses import dataclass

from .models import PlannedJourney


@dataclass(frozen=True)
class JourneySummary:
    distance_m: float
    shade_ratio_pct: float
    heat_level: str | None
    heat_explanation: str | None


def to_journey_summary(journey: PlannedJourney) -> JourneySummary:
    heat = journey.heat
    return JourneySummary(
        distance_m=journey.route.distance_m,
        shade_ratio_pct=journey.route.shade_ratio_pct,
        heat_level=heat.level if heat else None,
        heat_explanation=heat.explanation if heat else None,
    )
