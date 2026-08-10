"""Load and validate reproducible benchmark cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Coordinate:
    latitude: float
    longitude: float

    @classmethod
    def from_mapping(cls, value: dict[str, Any], field_name: str) -> "Coordinate":
        try:
            latitude = float(value["latitude"])
            longitude = float(value["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must contain numeric latitude/longitude") from exc

        if not -90 <= latitude <= 90:
            raise ValueError(f"{field_name}.latitude is outside -90..90")
        if not -180 <= longitude <= 180:
            raise ValueError(f"{field_name}.longitude is outside -180..180")
        return cls(latitude=latitude, longitude=longitude)


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    description: str
    category: str
    start: Coordinate
    destination: Coordinate
    departure_jst: datetime
    temperature_c: float
    sun_penalty: float
    expected_status: str
    expected_shadow_state: str
    required_metrics: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "BenchmarkCase":
        required = {
            "id",
            "description",
            "category",
            "start",
            "destination",
            "departure_jst",
            "temperature_c",
            "sun_penalty",
            "expectation",
        }
        missing = sorted(required - value.keys())
        if missing:
            raise ValueError(f"benchmark case is missing fields: {', '.join(missing)}")

        try:
            departure = datetime.fromisoformat(value["departure_jst"])
        except (TypeError, ValueError) as exc:
            raise ValueError("departure_jst must be an ISO 8601 datetime") from exc
        if departure.tzinfo is None:
            raise ValueError("departure_jst must include a timezone offset")

        expectation = value["expectation"]
        if not isinstance(expectation, dict):
            raise ValueError("expectation must be an object")

        expected_status = expectation.get("status")
        if expected_status not in {"route", "no_route", "out_of_scope"}:
            raise ValueError("expectation.status must be route, no_route, or out_of_scope")

        expected_shadow_state = expectation.get("shadow_state")
        if expected_shadow_state not in {"daylight", "night", "not_evaluated"}:
            raise ValueError(
                "expectation.shadow_state must be daylight, night, or not_evaluated"
            )

        metrics = expectation.get("required_metrics", [])
        if not isinstance(metrics, list) or not all(isinstance(item, str) for item in metrics):
            raise ValueError("expectation.required_metrics must be a list of strings")

        case_id = str(value["id"]).strip()
        if not case_id:
            raise ValueError("benchmark case id must not be empty")

        temperature_c = float(value["temperature_c"])
        sun_penalty = float(value["sun_penalty"])
        if sun_penalty < 1:
            raise ValueError("sun_penalty must be at least 1")

        return cls(
            case_id=case_id,
            description=str(value["description"]),
            category=str(value["category"]),
            start=Coordinate.from_mapping(value["start"], "start"),
            destination=Coordinate.from_mapping(value["destination"], "destination"),
            departure_jst=departure,
            temperature_c=temperature_c,
            sun_penalty=sun_penalty,
            expected_status=expected_status,
            expected_shadow_state=expected_shadow_state,
            required_metrics=tuple(metrics),
        )


def load_benchmark_cases(path: str | Path) -> list[BenchmarkCase]:
    """Load benchmark cases and reject duplicate identifiers."""
    source = Path(path)
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("cases"), list):
        raise ValueError("benchmark file must contain a cases list")

    cases = [BenchmarkCase.from_mapping(item) for item in raw["cases"]]
    ids = [case.case_id for case in cases]
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate benchmark case ids: {', '.join(duplicates)}")
    if not cases:
        raise ValueError("benchmark file must contain at least one case")
    return cases

