"""Small, dependency-free performance measurement utilities."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Iterator


@dataclass(frozen=True)
class TimingEvent:
    phase: str
    elapsed_seconds: float
    metadata: dict[str, Any]


class PerformanceRecorder:
    """Record named phases using a monotonic high-resolution clock."""

    def __init__(self, run_id: str, metadata: dict[str, Any] | None = None) -> None:
        if not run_id.strip():
            raise ValueError("run_id must not be empty")
        self.run_id = run_id
        self.metadata = dict(metadata or {})
        self.started_at = datetime.now(timezone.utc)
        self._started_perf = perf_counter()
        self.events: list[TimingEvent] = []

    @contextmanager
    def measure(self, phase: str, **metadata: Any) -> Iterator[None]:
        if not phase.strip():
            raise ValueError("phase must not be empty")
        started = perf_counter()
        try:
            yield
        finally:
            self.events.append(
                TimingEvent(
                    phase=phase,
                    elapsed_seconds=perf_counter() - started,
                    metadata=metadata,
                )
            )

    def as_dict(self) -> dict[str, Any]:
        event_sum = sum(event.elapsed_seconds for event in self.events)
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "started_at_utc": self.started_at.isoformat(),
            "metadata": self.metadata,
            "elapsed_wall_seconds": perf_counter() - self._started_perf,
            "sum_event_seconds": event_sum,
            "events": [asdict(event) for event in self.events],
        }

    def write_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.as_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return destination
