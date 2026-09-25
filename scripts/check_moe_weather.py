"""Manually verify the current official WBGT API contract."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.moe_weather import (
    JST,
    MoeHeatAlertClient,
    MoeWbgtClient,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--point", default="65042", help="環境省の地点番号")
    parser.add_argument("--region", default="300000", help="府県予報区等コード")
    args = parser.parse_args()
    now = datetime.now(JST).replace(second=0, microsecond=0)
    # Forecasts are updated around hh:30. Before that, query the previous issue hour.
    origin = now.replace(minute=0)
    if now.minute < 35:
        origin -= timedelta(hours=1)
    client = MoeWbgtClient(operation_period=(date(2026, 4, 22), date(2026, 10, 21)))
    forecast = client.fetch_forecast(args.point, origin, now)
    observations = client.fetch_observations(
        args.point, now - timedelta(hours=2), now, now
    )
    alert_url = _latest_alert_url(now)
    alerts = MoeHeatAlertClient().fetch_alerts(
        alert_url, now.date(), now, region_code=args.region
    )
    result = {
        "checked_at": now.isoformat(),
        "point_code": args.point,
        "forecast_count": len(forecast),
        "observation_count": len(observations),
        "forecast_sample": _reading(forecast[0]) if forecast else None,
        "observation_sample": _reading(_latest_available(observations)) if observations else None,
        "alert": _alert(alerts[0]) if alerts else None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _reading(reading) -> dict[str, object]:
    return {
        "value_celsius": reading.value_celsius,
        "value_kind": reading.value_kind.value,
        "quality_code": reading.quality_code,
        "reference_at": reading.reference_at.isoformat(),
        "valid_at": reading.valid_at.isoformat(),
        "retrieved_at": reading.retrieved_at.isoformat(),
        "status": reading.status.value,
        "source_url": reading.source_url,
    }


def _latest_available(readings):
    return next(
        (reading for reading in reversed(readings) if reading.value_celsius is not None),
        readings[-1],
    )


def _latest_alert_url(now: datetime) -> str:
    # Files are published "around" each scheduled hour; use a 10-minute grace.
    candidates = []
    for day_offset in (-1, 0):
        day = now.date() + timedelta(days=day_offset)
        for hour in (5, 10, 14, 17):
            candidates.append(
                datetime(day.year, day.month, day.day, hour, 10, tzinfo=JST)
            )
    publication = max(candidate for candidate in candidates if candidate <= now)
    filename = f"alert_{publication:%Y%m%d}_{publication:%H}.csv"
    return f"https://www.wbgt.env.go.jp/alert/dl/{publication:%Y}/{filename}"


def _alert(alert) -> dict[str, object]:
    return {
        "region_code": alert.region_code,
        "region_name": alert.region_name,
        "kind": alert.kind.value,
        "status": alert.status.value,
        "freshness": alert.freshness.value,
        "issued_at": alert.issued_at.isoformat(),
        "target_start": alert.target_start.isoformat(),
        "target_end": alert.target_end.isoformat(),
        "retrieved_at": alert.retrieved_at.isoformat(),
        "source_url": alert.source_url,
    }


if __name__ == "__main__":
    main()
