"""Boundary for heat-risk evaluation."""

from __future__ import annotations

from typing import Protocol

from .models import HeatAssessment, RouteRequest, RouteResult


class HeatEvaluator(Protocol):
    def evaluate(self, request: RouteRequest, route: RouteResult) -> HeatAssessment:
        """Evaluate heat exposure without prescribing a particular weather source."""
