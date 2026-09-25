"""UI-neutral contracts for official heat information and caching."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Callable, Generic, Hashable, Protocol, TypeVar


class WbgtValueKind(str, Enum):
    FORECAST = "forecast"
    ESTIMATED_ACTUAL = "estimated_actual"
    MEASURED_ACTUAL = "measured_actual"


class DataStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"
    OUTSIDE_OPERATION = "outside_operation"


class AlertKind(str, Enum):
    HEAT_ALERT = "heat_alert"
    SPECIAL_HEAT_ALERT = "special_heat_alert"


class AlertStatus(str, Enum):
    ISSUED = "issued"
    NOT_ISSUED = "not_issued"
    SPECIAL_ASSESSMENT = "special_assessment"
    OUTSIDE_OPERATION = "outside_operation"
    TRAINING = "training"
    TEST = "test"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class OfficialWbgtReading:
    source_id: str
    source_url: str
    point_code: str
    value_celsius: float | None
    value_kind: WbgtValueKind
    quality_code: str
    reference_at: datetime
    valid_at: datetime
    retrieved_at: datetime
    status: DataStatus = DataStatus.CURRENT
    point_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    def __post_init__(self) -> None:
        _require_aware(self.reference_at, "reference_at")
        _require_aware(self.valid_at, "valid_at")
        _require_aware(self.retrieved_at, "retrieved_at")
        if not self.point_code:
            raise ValueError("point_code is required")

    def with_status(self, status: DataStatus) -> OfficialWbgtReading:
        return replace(self, status=status)


@dataclass(frozen=True)
class OfficialHeatAlert:
    source_id: str
    source_url: str
    region_code: str
    region_name: str
    kind: AlertKind
    status: AlertStatus
    issued_at: datetime
    target_start: datetime
    target_end: datetime
    retrieved_at: datetime
    publication_id: str
    freshness: DataStatus = DataStatus.CURRENT

    def __post_init__(self) -> None:
        for name in ("issued_at", "target_start", "target_end", "retrieved_at"):
            _require_aware(getattr(self, name), name)
        if self.target_end < self.target_start:
            raise ValueError("target_end must not precede target_start")

    def with_freshness(self, freshness: DataStatus) -> OfficialHeatAlert:
        return replace(self, freshness=freshness)


class WeatherDataError(RuntimeError):
    """Base error for official heat-data acquisition."""


class WeatherDataTimedOut(WeatherDataError):
    """The official service did not answer before the timeout."""


class WeatherDataRateLimited(WeatherDataError):
    """The official service rejected requests due to rate limiting."""


class WeatherDataUnavailable(WeatherDataError):
    """The official service or requested publication is unavailable."""


class WeatherDataInvalid(WeatherDataError):
    """The response does not match the documented contract."""


class WbgtDataSource(Protocol):
    def fetch_forecast(
        self, point_code: str, origin_at: datetime, retrieved_at: datetime
    ) -> tuple[OfficialWbgtReading, ...]: ...

    def fetch_observations(
        self,
        point_code: str,
        start_at: datetime,
        end_at: datetime,
        retrieved_at: datetime,
    ) -> tuple[OfficialWbgtReading, ...]: ...


class HeatAlertDataSource(Protocol):
    def fetch_alerts(
        self,
        publication_url: str,
        target_date: date,
        retrieved_at: datetime,
        *,
        region_code: str | None = None,
    ) -> tuple[OfficialHeatAlert, ...]: ...


T = TypeVar("T")


@dataclass(frozen=True)
class CacheResult(Generic[T]):
    value: T
    cache_hit: bool
    stale: bool
    error: WeatherDataError | None = None


@dataclass
class _CacheEntry(Generic[T]):
    value: T
    stored_at: datetime


class TimedWeatherCache(Generic[T]):
    """Small in-memory TTL cache with explicit stale-on-error fallback."""

    def __init__(self, ttl: timedelta = timedelta(minutes=20)) -> None:
        if ttl <= timedelta(0):
            raise ValueError("ttl must be positive")
        self.ttl = ttl
        self._entries: dict[Hashable, _CacheEntry[T]] = {}

    def get_or_load(
        self,
        key: Hashable,
        loader: Callable[[], T],
        now: datetime,
        *,
        mark_stale: Callable[[T], T],
    ) -> CacheResult[T]:
        _require_aware(now, "now")
        entry = self._entries.get(key)
        if entry is not None and now - entry.stored_at < self.ttl:
            return CacheResult(entry.value, cache_hit=True, stale=False)
        try:
            value = loader()
        except WeatherDataError as error:
            if entry is None:
                raise
            return CacheResult(
                mark_stale(entry.value), cache_hit=True, stale=True, error=error
            )
        self._entries[key] = _CacheEntry(value, now)
        return CacheResult(value, cache_hit=False, stale=False)

    def clear(self) -> None:
        self._entries.clear()


@dataclass(frozen=True)
class HeatInformation:
    wbgt: tuple[OfficialWbgtReading, ...]
    alerts: tuple[OfficialHeatAlert, ...]
    problems: tuple[str, ...]


class OfficialHeatInformationService:
    """Loads independent WBGT and alert streams without blocking route use."""

    def __init__(
        self,
        wbgt_source: WbgtDataSource,
        alert_source: HeatAlertDataSource,
        *,
        cache_ttl: timedelta = timedelta(minutes=20),
    ) -> None:
        self._wbgt_source = wbgt_source
        self._alert_source = alert_source
        self._wbgt_cache: TimedWeatherCache[tuple[OfficialWbgtReading, ...]] = (
            TimedWeatherCache(cache_ttl)
        )
        self._alert_cache: TimedWeatherCache[tuple[OfficialHeatAlert, ...]] = (
            TimedWeatherCache(cache_ttl)
        )

    def load(
        self,
        *,
        point_code: str,
        origin_at: datetime,
        alert_publication_url: str,
        alert_target_date: date,
        now: datetime,
        region_code: str | None = None,
    ) -> HeatInformation:
        _require_aware(origin_at, "origin_at")
        _require_aware(now, "now")
        problems: list[str] = []
        wbgt: tuple[OfficialWbgtReading, ...] = ()
        alerts: tuple[OfficialHeatAlert, ...] = ()

        try:
            forecast_result = self._wbgt_cache.get_or_load(
                ("forecast", point_code, origin_at),
                lambda: self._wbgt_source.fetch_forecast(
                    point_code, origin_at, now
                ),
                now,
                mark_stale=lambda readings: tuple(
                    reading.with_status(DataStatus.STALE) for reading in readings
                ),
            )
            wbgt = _apply_wbgt_freshness(forecast_result.value, now)
            if forecast_result.error:
                problems.append(
                    _problem_message("WBGT予測", forecast_result.error, stale=True)
                )
        except WeatherDataError as error:
            problems.append(_problem_message("WBGT予測", error, stale=False))

        observation_start = now - timedelta(hours=2)
        try:
            observation_result = self._wbgt_cache.get_or_load(
                ("observation", point_code),
                lambda: self._wbgt_source.fetch_observations(
                    point_code, observation_start, now, now
                ),
                now,
                mark_stale=lambda readings: tuple(
                    reading.with_status(DataStatus.STALE) for reading in readings
                ),
            )
            wbgt += _apply_wbgt_freshness(observation_result.value, now)
            if observation_result.error:
                problems.append(
                    _problem_message("WBGT実況", observation_result.error, stale=True)
                )
        except WeatherDataError as error:
            problems.append(_problem_message("WBGT実況", error, stale=False))

        try:
            result = self._alert_cache.get_or_load(
                ("alert", alert_publication_url, alert_target_date, region_code),
                lambda: self._alert_source.fetch_alerts(
                    alert_publication_url,
                    alert_target_date,
                    now,
                    region_code=region_code,
                ),
                now,
                mark_stale=lambda items: tuple(
                    item.with_freshness(DataStatus.STALE) for item in items
                ),
            )
            alerts = result.value
            if result.error:
                problems.append(_problem_message("警戒情報", result.error, stale=True))
        except WeatherDataError as error:
            problems.append(_problem_message("警戒情報", error, stale=False))

        return HeatInformation(wbgt, alerts, tuple(problems))


def _apply_wbgt_freshness(
    readings: tuple[OfficialWbgtReading, ...], now: datetime
) -> tuple[OfficialWbgtReading, ...]:
    refreshed = []
    for reading in readings:
        if reading.status is not DataStatus.CURRENT:
            refreshed.append(reading)
            continue
        limit = (
            timedelta(minutes=90)
            if reading.value_kind is WbgtValueKind.FORECAST
            else timedelta(minutes=60)
        )
        age_from = (
            reading.reference_at
            if reading.value_kind is WbgtValueKind.FORECAST
            else reading.valid_at
        )
        refreshed.append(
            reading.with_status(DataStatus.STALE)
            if now - age_from > limit
            else reading
        )
    return tuple(refreshed)


def _problem_message(label: str, error: WeatherDataError, *, stale: bool) -> str:
    suffix = "最後に取得した期限切れデータを表示します。" if stale else "情報を表示できません。経路検索は利用できます。"
    return f"{label}の取得に失敗しました（{type(error).__name__}）。{suffix}"


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include timezone information")
