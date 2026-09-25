"""Adapters for Japan Ministry of the Environment WBGT services."""

from __future__ import annotations

from collections.abc import Callable
import csv
from datetime import date, datetime, timedelta, timezone
import io
import json
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..weather import (
    AlertKind,
    AlertStatus,
    DataStatus,
    OfficialHeatAlert,
    OfficialWbgtReading,
    WbgtValueKind,
    WeatherDataInvalid,
    WeatherDataRateLimited,
    WeatherDataTimedOut,
    WeatherDataUnavailable,
)


JST = timezone(timedelta(hours=9), name="JST")
MOE_SOURCE_ID = "moe-wbgt"
FORECAST_URL = "https://www.wbgt.env.go.jp/api/v1/getForecastData"
SURVEY_URL = "https://www.wbgt.env.go.jp/api/v1/getSurveyData"


class RetryingHttpTransport:
    """HTTPS GET transport with bounded retries and injectable test hooks."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 5.0,
        attempts: int = 3,
        backoff_seconds: float = 0.25,
        user_agent: str = "KAGE-MICHI/official-heat-data",
        opener: Callable[[str, float, str], bytes] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_seconds <= 0 or attempts < 1 or backoff_seconds < 0:
            raise ValueError("invalid HTTP retry settings")
        self.timeout_seconds = timeout_seconds
        self.attempts = attempts
        self.backoff_seconds = backoff_seconds
        self.user_agent = user_agent
        self._opener = opener or _urlopen_bytes
        self._sleeper = sleeper

    def get(self, url: str) -> bytes:
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                return self._opener(url, self.timeout_seconds, self.user_agent)
            except HTTPError as error:
                if error.code == 429:
                    mapped = WeatherDataRateLimited("official service rate limited")
                elif 500 <= error.code < 600:
                    mapped = WeatherDataUnavailable(
                        f"official service returned HTTP {error.code}"
                    )
                else:
                    raise WeatherDataUnavailable(
                        f"official service returned HTTP {error.code}"
                    ) from error
                last_error = mapped
            except (TimeoutError, socket.timeout) as error:
                last_error = WeatherDataTimedOut("official service timed out")
                last_error.__cause__ = error
            except URLError as error:
                last_error = WeatherDataUnavailable("official service unavailable")
                last_error.__cause__ = error
            if attempt + 1 < self.attempts:
                self._sleeper(self.backoff_seconds * (2**attempt))
        assert last_error is not None
        raise last_error


class MoeWbgtClient:
    def __init__(
        self,
        transport: RetryingHttpTransport | None = None,
        *,
        operation_period: tuple[date, date] | None = None,
    ) -> None:
        self._transport = transport or RetryingHttpTransport()
        if operation_period and operation_period[1] < operation_period[0]:
            raise ValueError("operation period end must not precede start")
        self._operation_period = operation_period

    def fetch_forecast(
        self, point_code: str, origin_at: datetime, retrieved_at: datetime
    ) -> tuple[OfficialWbgtReading, ...]:
        _require_aware(origin_at, "origin_at")
        _require_aware(retrieved_at, "retrieved_at")
        if self._is_outside_operation(origin_at.date()):
            return (
                _outside_operation_reading(
                    point_code, origin_at, retrieved_at, WbgtValueKind.FORECAST
                ),
            )
        params = [
            ("location_type", "1"),
            ("date_search_type", "3"),
            ("wbgt_nos", point_code),
            ("forecast_origin_date", origin_at.astimezone(JST).strftime("%Y%m%d%H%M%S")),
        ]
        url = f"{FORECAST_URL}?{urlencode(params)}"
        payload = _load_json(self._transport.get(url))
        rows = _success_rows(payload)
        if not rows:
            return (
                _missing_reading(
                    point_code,
                    url,
                    origin_at,
                    retrieved_at,
                    WbgtValueKind.FORECAST,
                ),
            )
        readings = []
        for row in rows:
            value = _optional_number(row.get("forecast_val"), scale=10)
            readings.append(
                OfficialWbgtReading(
                    source_id=MOE_SOURCE_ID,
                    source_url=url,
                    point_code=str(row.get("wbgt_no", point_code)),
                    value_celsius=value,
                    value_kind=WbgtValueKind.FORECAST,
                    quality_code=_text_or_empty(row.get("flag")),
                    reference_at=_parse_moe_datetime(row.get("reference_time")),
                    valid_at=_parse_moe_datetime(row.get("forecast_time")),
                    retrieved_at=retrieved_at,
                    status=DataStatus.MISSING if value is None else DataStatus.CURRENT,
                )
            )
        return tuple(readings)

    def fetch_observations(
        self,
        point_code: str,
        start_at: datetime,
        end_at: datetime,
        retrieved_at: datetime,
    ) -> tuple[OfficialWbgtReading, ...]:
        for name, value in (
            ("start_at", start_at),
            ("end_at", end_at),
            ("retrieved_at", retrieved_at),
        ):
            _require_aware(value, name)
        if end_at < start_at:
            raise ValueError("end_at must not precede start_at")
        if self._is_outside_operation(start_at.date()) and self._is_outside_operation(
            end_at.date()
        ):
            return (
                _outside_operation_reading(
                    point_code,
                    end_at,
                    retrieved_at,
                    WbgtValueKind.ESTIMATED_ACTUAL,
                ),
            )
        params = [
            ("data_type", "0"),
            ("data_type", "1"),
            ("location_type", "1"),
            ("wbgt_nos", point_code),
            ("date_from", start_at.astimezone(JST).strftime("%Y%m%d%H%M%S")),
            ("date_to", end_at.astimezone(JST).strftime("%Y%m%d%H%M%S")),
        ]
        url = f"{SURVEY_URL}?{urlencode(params)}"
        rows = _success_rows(_load_json(self._transport.get(url)))
        if not rows:
            return (
                _missing_reading(
                    point_code,
                    url,
                    end_at,
                    retrieved_at,
                    WbgtValueKind.ESTIMATED_ACTUAL,
                ),
            )
        readings = []
        for row in rows:
            value = _optional_number(row.get("wbgt_WO"))
            valid_at = _parse_moe_datetime(row.get("wbgt_date"))
            value_kind = (
                WbgtValueKind.MEASURED_ACTUAL
                if int(row.get("wbgt_class", 0)) == 1
                else WbgtValueKind.ESTIMATED_ACTUAL
            )
            readings.append(
                OfficialWbgtReading(
                    source_id=MOE_SOURCE_ID,
                    source_url=url,
                    point_code=str(row.get("wbgt_no", point_code)),
                    value_celsius=value,
                    value_kind=value_kind,
                    quality_code=_text_or_empty(row.get("wbgt_WI")),
                    reference_at=valid_at,
                    valid_at=valid_at,
                    retrieved_at=retrieved_at,
                    status=DataStatus.MISSING if value is None else DataStatus.CURRENT,
                )
            )
        return tuple(readings)

    def _is_outside_operation(self, target: date) -> bool:
        if self._operation_period is None:
            return False
        start, end = self._operation_period
        return not start <= target <= end


class MoeHeatAlertClient:
    def __init__(self, transport: RetryingHttpTransport | None = None) -> None:
        self._transport = transport or RetryingHttpTransport()

    def fetch_alerts(
        self,
        publication_url: str,
        target_date: date,
        retrieved_at: datetime,
        *,
        region_code: str | None = None,
    ) -> tuple[OfficialHeatAlert, ...]:
        _require_aware(retrieved_at, "retrieved_at")
        try:
            text = self._transport.get(publication_url).decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise WeatherDataInvalid("alert CSV is not UTF-8") from error
        return parse_alert_csv(
            text,
            publication_url=publication_url,
            target_date=target_date,
            retrieved_at=retrieved_at,
            region_code=region_code,
        )


def parse_alert_csv(
    text: str,
    *,
    publication_url: str,
    target_date: date,
    retrieved_at: datetime,
    region_code: str | None = None,
) -> tuple[OfficialHeatAlert, ...]:
    _require_aware(retrieved_at, "retrieved_at")
    rows = [row for row in csv.reader(io.StringIO(text)) if row]
    meta: dict[str, str] = {}
    data_rows: list[list[str]] = []
    for row in rows:
        key = row[0].lstrip("#").strip()
        if key in {
            "Title", "Encoding", "TimeZone", "CreateDate", "CreateTime",
            "PublishingOffice", "ReportDate", "ReportTime", "TargetDate1",
            "TargetTime1", "DurationTime1", "TargetDate2", "TargetTime2",
            "DurationTime2", "Status", "InternalFlag",
        }:
            meta[key] = row[1].strip() if len(row) > 1 else ""
        elif len(row) >= 8 and row[3].strip().isdigit():
            data_rows.append(row)
    if not data_rows:
        raise WeatherDataInvalid("alert CSV contains no region rows")

    target_index = _target_index(meta, target_date)
    issued_at = _meta_datetime(meta, "ReportDate", "ReportTime")
    target_start = _meta_datetime(
        meta, f"TargetDate{target_index}", f"TargetTime{target_index}"
    )
    duration = _parse_duration(meta.get(f"DurationTime{target_index}", "24:00:00"))
    operation_status = meta.get("Status", "通常").strip()
    publication_id = meta.get("InternalFlag") or issued_at.isoformat()
    alerts = []
    for row in data_rows:
        code = row[3].strip()
        if region_code is not None and code != region_code:
            continue
        flag = _parse_flag(row[6 if target_index == 1 else 7])
        kind, status = _alert_state(flag, operation_status)
        alerts.append(
            OfficialHeatAlert(
                source_id=MOE_SOURCE_ID,
                source_url=publication_url,
                region_code=code,
                region_name=row[0].strip(),
                kind=kind,
                status=status,
                issued_at=issued_at,
                target_start=target_start,
                target_end=target_start + duration,
                retrieved_at=retrieved_at,
                publication_id=publication_id,
            )
        )
    if region_code is not None and not alerts:
        raise WeatherDataUnavailable(f"region {region_code} is absent from alert CSV")
    return tuple(alerts)


def _alert_state(flag: int, operation_status: str) -> tuple[AlertKind, AlertStatus]:
    mapping = {
        0: (AlertKind.HEAT_ALERT, AlertStatus.NOT_ISSUED),
        1: (AlertKind.HEAT_ALERT, AlertStatus.ISSUED),
        2: (AlertKind.SPECIAL_HEAT_ALERT, AlertStatus.SPECIAL_ASSESSMENT),
        3: (AlertKind.SPECIAL_HEAT_ALERT, AlertStatus.ISSUED),
        9: (AlertKind.HEAT_ALERT, AlertStatus.OUTSIDE_OPERATION),
    }
    try:
        kind, status = mapping[flag]
    except KeyError as error:
        raise WeatherDataInvalid(f"unsupported alert flag: {flag}") from error
    if operation_status == "訓練":
        return kind, AlertStatus.TRAINING
    if operation_status == "試験":
        return kind, AlertStatus.TEST
    return kind, status


def _success_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise WeatherDataUnavailable("WBGT API returned an error status")
    rows = payload.get("data")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise WeatherDataInvalid("WBGT API data must be a list of objects")
    return rows


def _load_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WeatherDataInvalid("WBGT API response is not valid UTF-8 JSON") from error


def _optional_number(value: Any, *, scale: float = 1) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value) / scale
    except (TypeError, ValueError) as error:
        raise WeatherDataInvalid(f"invalid WBGT value: {value!r}") from error


def _text_or_empty(value: Any) -> str:
    return "" if value is None else str(value)


def _parse_moe_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise WeatherDataInvalid("documented datetime field is missing")
    try:
        return datetime.strptime(value, "%Y/%m/%d %H:%M:%S").replace(tzinfo=JST)
    except ValueError as error:
        raise WeatherDataInvalid(f"invalid documented datetime: {value!r}") from error


def _meta_datetime(meta: dict[str, str], date_key: str, time_key: str) -> datetime:
    return _parse_moe_datetime(f"{meta.get(date_key, '')} {meta.get(time_key, '')}")


def _target_index(meta: dict[str, str], target_date: date) -> int:
    formatted = target_date.strftime("%Y/%m/%d")
    if meta.get("TargetDate1") == formatted:
        return 1
    if meta.get("TargetDate2") == formatted:
        return 2
    raise WeatherDataUnavailable("requested target date is absent from alert CSV")


def _parse_duration(value: str) -> timedelta:
    try:
        hours, minutes, seconds = (int(part) for part in value.split(":"))
    except (ValueError, TypeError) as error:
        raise WeatherDataInvalid(f"invalid alert duration: {value!r}") from error
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def _parse_flag(value: str) -> int:
    try:
        return int(value.strip())
    except (AttributeError, ValueError) as error:
        raise WeatherDataInvalid(f"invalid alert flag: {value!r}") from error


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include timezone information")


def _urlopen_bytes(url: str, timeout: float, user_agent: str) -> bytes:
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _outside_operation_reading(
    point_code: str,
    target_at: datetime,
    retrieved_at: datetime,
    value_kind: WbgtValueKind,
) -> OfficialWbgtReading:
    return OfficialWbgtReading(
        source_id=MOE_SOURCE_ID,
        source_url="https://www.wbgt.env.go.jp/data_service.php",
        point_code=point_code,
        value_celsius=None,
        value_kind=value_kind,
        quality_code="",
        reference_at=target_at,
        valid_at=target_at,
        retrieved_at=retrieved_at,
        status=DataStatus.OUTSIDE_OPERATION,
    )


def _missing_reading(
    point_code: str,
    source_url: str,
    target_at: datetime,
    retrieved_at: datetime,
    value_kind: WbgtValueKind,
) -> OfficialWbgtReading:
    return OfficialWbgtReading(
        source_id=MOE_SOURCE_ID,
        source_url=source_url,
        point_code=point_code,
        value_celsius=None,
        value_kind=value_kind,
        quality_code="",
        reference_at=target_at,
        valid_at=target_at,
        retrieved_at=retrieved_at,
        status=DataStatus.MISSING,
    )
