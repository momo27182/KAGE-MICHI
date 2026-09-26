"""Records and summaries for field validation of estimated road shade."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime
import csv
import json
import math
from pathlib import Path
from statistics import mean


VALIDATION_SCHEMA_VERSION = 1
VALID_WEATHER = {"sunny", "mostly_sunny", "cloudy", "variable"}
VALID_SHADE_SOURCES = {"building", "tree", "eave", "terrain", "other", "none"}


@dataclass(frozen=True)
class FieldObservation:
    observation_id: str
    location_name: str
    latitude: float
    longitude: float
    observed_at: str
    predicted_shade_pct: float
    observed_shade_pct: float
    weather: str
    shade_source: str
    photo_reference: str = ""
    camera_direction_deg: float | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("observation_id is required")
        if not self.location_name.strip():
            raise ValueError("location_name is required")
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ValueError("latitude or longitude is outside the valid range")
        observed_at = datetime.fromisoformat(self.observed_at)
        if observed_at.utcoffset() is None:
            raise ValueError("observed_at must include timezone information")
        for name, value in (
            ("predicted_shade_pct", self.predicted_shade_pct),
            ("observed_shade_pct", self.observed_shade_pct),
        ):
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError(f"{name} must be between 0 and 100")
        if self.weather not in VALID_WEATHER:
            raise ValueError(f"weather must be one of {sorted(VALID_WEATHER)}")
        if self.shade_source not in VALID_SHADE_SOURCES:
            raise ValueError(f"shade_source must be one of {sorted(VALID_SHADE_SOURCES)}")
        if self.camera_direction_deg is not None and not 0 <= self.camera_direction_deg < 360:
            raise ValueError("camera_direction_deg must be at least 0 and less than 360")

    @property
    def error_percentage_points(self) -> float:
        return self.predicted_shade_pct - self.observed_shade_pct


def write_observation_template(destination: str | Path) -> Path:
    """Write a UTF-8 CSV template with one example row for field use."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    example = FieldObservation(
        observation_id="example-001",
        location_name="和歌山駅西口",
        latitude=34.2325,
        longitude=135.1917,
        observed_at="2026-08-11T14:00:00+09:00",
        predicted_shade_pct=40.0,
        observed_shade_pct=35.0,
        weather="sunny",
        shade_source="building",
        photo_reference="photos/example-001.jpg",
        camera_direction_deg=90.0,
        notes="記入例。実測時は削除または上書きする。",
    )
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[field.name for field in fields(FieldObservation)])
        writer.writeheader()
        writer.writerow(asdict(example))
    return path


def read_observations(source: str | Path) -> list[FieldObservation]:
    """Read and validate observations from the versioned CSV contract."""
    path = Path(source)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = [field.name for field in fields(FieldObservation)]
        if reader.fieldnames != expected:
            raise ValueError(f"CSV columns must be exactly: {', '.join(expected)}")
        observations = [_observation_from_row(row, line_number) for line_number, row in enumerate(reader, 2)]
    if not observations:
        raise ValueError("CSV must contain at least one observation")
    ids = [item.observation_id for item in observations]
    if len(ids) != len(set(ids)):
        raise ValueError("observation_id values must be unique")
    return observations


def summarize_observations(observations: list[FieldObservation]) -> dict[str, object]:
    """Create reproducible error metrics without claiming model safety."""
    if not observations:
        raise ValueError("at least one observation is required")
    errors = [item.error_percentage_points for item in observations]
    absolute_errors = [abs(error) for error in errors]
    by_source: dict[str, list[float]] = {}
    for item, error in zip(observations, absolute_errors, strict=True):
        by_source.setdefault(item.shade_source, []).append(error)
    return {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "observation_count": len(observations),
        "location_count": len({(item.latitude, item.longitude) for item in observations}),
        "mean_error_percentage_points": round(mean(errors), 3),
        "mean_absolute_error_percentage_points": round(mean(absolute_errors), 3),
        "max_absolute_error_percentage_points": round(max(absolute_errors), 3),
        "within_10_percentage_points_count": sum(error <= 10 for error in absolute_errors),
        "by_shade_source": {
            source: {
                "count": len(source_errors),
                "mean_absolute_error_percentage_points": round(mean(source_errors), 3),
            }
            for source, source_errors in sorted(by_source.items())
        },
        "limitations": [
            "Observed shade percentage is a field estimate unless a separate measurement method is documented.",
            "This summary does not establish medical safety or accuracy outside the recorded locations and times.",
            "Cloud changes can make predicted and observed shade incomparable; weather must be reviewed with photos.",
        ],
    }


def write_validation_report(report: dict[str, object], destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _observation_from_row(row: dict[str, str], line_number: int) -> FieldObservation:
    try:
        direction = row["camera_direction_deg"].strip()
        return FieldObservation(
            observation_id=row["observation_id"].strip(),
            location_name=row["location_name"].strip(),
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            observed_at=row["observed_at"].strip(),
            predicted_shade_pct=float(row["predicted_shade_pct"]),
            observed_shade_pct=float(row["observed_shade_pct"]),
            weather=row["weather"].strip(),
            shade_source=row["shade_source"].strip(),
            photo_reference=row["photo_reference"].strip(),
            camera_direction_deg=float(direction) if direction else None,
            notes=row["notes"].strip(),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid observation at CSV line {line_number}: {exc}") from exc
