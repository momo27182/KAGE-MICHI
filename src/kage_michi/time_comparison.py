"""UI-independent rules for comparing routes at two departure times."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .infrastructure.precomputed_shade import MANIFEST_FILE


@dataclass(frozen=True)
class ShadeArtifactReference:
    directory: Path
    version: str


def default_comparison_datetime(departure: datetime) -> datetime:
    """Default to one hour later while preserving timezone and date rollover."""
    _require_aware(departure, "departure")
    return departure + timedelta(hours=1)


def validate_comparison_datetimes(
    departure: datetime, comparison: datetime
) -> None:
    _require_aware(departure, "departure")
    _require_aware(comparison, "comparison")
    if departure == comparison:
        raise ValueError("比較日時は基準日時と異なる日時を指定してください。")


def resolve_shade_artifact(
    shade_root: str | Path, requested: datetime
) -> ShadeArtifactReference:
    """Resolve and version the artifact for the requested local calendar date."""
    _require_aware(requested, "requested")
    directory = Path(shade_root).resolve() / requested.date().isoformat()
    manifest = directory / MANIFEST_FILE
    if not manifest.is_file():
        raise FileNotFoundError(
            "事前計算済み日陰率がありません: "
            f"対象日時={requested.isoformat()}, path={manifest}"
        )
    return ShadeArtifactReference(directory, str(manifest.stat().st_mtime_ns))


def _require_aware(value: datetime, name: str) -> None:
    if value.utcoffset() is None:
        raise ValueError(f"{name} must include timezone information")
