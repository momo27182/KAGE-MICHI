"""Application use cases that orchestrate product boundaries."""

from __future__ import annotations

from dataclasses import dataclass

from .data import SpatialDataSource
from .heat import HeatEvaluator
from .models import PlannedJourney, RouteRequest
from .routing import RoutePlanner
from .shadows import ShadowCalculator


@dataclass
class PlanJourney:
    data_source: SpatialDataSource
    shadow_calculator: ShadowCalculator
    route_planner: RoutePlanner
    heat_evaluator: HeatEvaluator | None = None

    def execute(self, request: RouteRequest) -> PlannedJourney:
        dataset = self.data_source.load(request.start, request.destination)
        shadows = self.shadow_calculator.calculate(dataset, request.departure)
        route = self.route_planner.find_route(
            dataset,
            request.start,
            request.destination,
            shadows,
        )
        heat = (
            self.heat_evaluator.evaluate(request, route)
            if self.heat_evaluator is not None
            else None
        )
        return PlannedJourney(route=route, heat=heat)
