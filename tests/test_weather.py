from datetime import date, datetime, timedelta
from pathlib import Path
import sys
import unittest
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.moe_weather import (
    FORECAST_URL,
    JST,
    MoeHeatAlertClient,
    MoeWbgtClient,
    RetryingHttpTransport,
    parse_alert_csv,
)
from kage_michi.weather import (
    AlertKind,
    AlertStatus,
    DataStatus,
    OfficialWbgtReading,
    OfficialHeatInformationService,
    TimedWeatherCache,
    WbgtValueKind,
    WeatherDataRateLimited,
    WeatherDataInvalid,
    WeatherDataTimedOut,
    WeatherDataUnavailable,
)


FIXTURES = ROOT / "tests" / "fixtures" / "weather"
NOW = datetime(2026, 9, 25, 16, 5, tzinfo=JST)


class StaticTransport:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.urls = []

    def get(self, url: str) -> bytes:
        self.urls.append(url)
        return self.payload


class MoeWbgtClientTests(unittest.TestCase):
    def test_forecast_uses_documented_tenths_and_preserves_missing(self) -> None:
        transport = StaticTransport((FIXTURES / "forecast.json").read_bytes())
        client = MoeWbgtClient(transport)

        readings = client.fetch_forecast("65042", NOW.replace(minute=0), NOW)

        self.assertEqual(len(readings), 2)
        self.assertEqual(readings[0].value_celsius, 28.7)
        self.assertEqual(readings[0].value_kind, WbgtValueKind.FORECAST)
        self.assertEqual(readings[0].status, DataStatus.CURRENT)
        self.assertIsNone(readings[1].value_celsius)
        self.assertEqual(readings[1].status, DataStatus.MISSING)
        self.assertIn(FORECAST_URL, readings[0].source_url)
        self.assertIn("forecast_origin_date=20260925160000", transport.urls[0])

    def test_observations_keep_estimated_and_measured_values_distinct(self) -> None:
        transport = StaticTransport((FIXTURES / "survey.json").read_bytes())
        client = MoeWbgtClient(transport)

        readings = client.fetch_observations(
            "65042", NOW - timedelta(hours=2), NOW, NOW
        )

        self.assertEqual([item.value_celsius for item in readings], [28.6, None, 28.1])
        self.assertEqual(
            [item.value_kind for item in readings],
            [
                WbgtValueKind.ESTIMATED_ACTUAL,
                WbgtValueKind.MEASURED_ACTUAL,
                WbgtValueKind.MEASURED_ACTUAL,
            ],
        )
        self.assertEqual(readings[1].quality_code, "")
        self.assertEqual(readings[1].status, DataStatus.MISSING)
        self.assertEqual(readings[2].quality_code, "3.0")

    def test_invalid_json_is_not_silently_treated_as_missing(self) -> None:
        client = MoeWbgtClient(StaticTransport(b"not-json"))
        with self.assertRaises(WeatherDataInvalid):
            client.fetch_forecast("65042", NOW, NOW)

    def test_configured_operation_period_avoids_request_and_marks_state(self) -> None:
        transport = StaticTransport(b"must not be requested")
        client = MoeWbgtClient(
            transport, operation_period=(date(2026, 4, 22), date(2026, 10, 21))
        )

        readings = client.fetch_forecast(
            "65042", datetime(2026, 11, 1, 12, tzinfo=JST), NOW
        )

        self.assertEqual(readings[0].status, DataStatus.OUTSIDE_OPERATION)
        self.assertEqual(transport.urls, [])

    def test_successful_empty_responses_are_explicitly_missing(self) -> None:
        empty = StaticTransport(b'{"status":"success","data":[],"count":0}')
        client = MoeWbgtClient(empty)

        forecast = client.fetch_forecast("65042", NOW, NOW)
        observations = client.fetch_observations(
            "65042", NOW - timedelta(hours=2), NOW, NOW
        )

        self.assertEqual(forecast[0].status, DataStatus.MISSING)
        self.assertEqual(observations[0].status, DataStatus.MISSING)
        self.assertIsNone(forecast[0].value_celsius)
        self.assertIsNone(observations[0].value_celsius)


class MoeHeatAlertClientTests(unittest.TestCase):
    def test_alert_csv_distinguishes_issued_and_special_assessment(self) -> None:
        text = (FIXTURES / "alert.csv").read_text(encoding="utf-8")

        today = parse_alert_csv(
            text,
            publication_url="https://example.test/alert.csv",
            target_date=date(2026, 9, 25),
            retrieved_at=NOW,
            region_code="300000",
        )
        tomorrow = parse_alert_csv(
            text,
            publication_url="https://example.test/alert.csv",
            target_date=date(2026, 9, 26),
            retrieved_at=NOW,
            region_code="300000",
        )

        self.assertEqual(today[0].kind, AlertKind.HEAT_ALERT)
        self.assertEqual(today[0].status, AlertStatus.ISSUED)
        self.assertEqual(tomorrow[0].kind, AlertKind.SPECIAL_HEAT_ALERT)
        self.assertEqual(tomorrow[0].status, AlertStatus.SPECIAL_ASSESSMENT)
        self.assertEqual(tomorrow[0].freshness, DataStatus.CURRENT)
        self.assertEqual(
            tomorrow[0].with_freshness(DataStatus.STALE).status,
            AlertStatus.SPECIAL_ASSESSMENT,
        )
        self.assertEqual(today[0].target_end - today[0].target_start, timedelta(days=1))

    def test_alert_client_reports_absent_region(self) -> None:
        transport = StaticTransport((FIXTURES / "alert.csv").read_bytes())
        client = MoeHeatAlertClient(transport)
        with self.assertRaises(WeatherDataUnavailable):
            client.fetch_alerts(
                "https://example.test/alert.csv",
                date(2026, 9, 25),
                NOW,
                region_code="999999",
            )


class WeatherCacheTests(unittest.TestCase):
    def test_twenty_minute_cache_reuses_identical_request(self) -> None:
        cache = TimedWeatherCache(timedelta(minutes=20))
        calls = []

        def load():
            calls.append("load")
            return ("value",)

        first = cache.get_or_load("same", load, NOW, mark_stale=lambda value: value)
        second = cache.get_or_load(
            "same", load, NOW + timedelta(minutes=19), mark_stale=lambda value: value
        )

        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(calls, ["load"])

    def test_expired_cache_is_marked_stale_when_refresh_fails(self) -> None:
        cache = TimedWeatherCache(timedelta(minutes=20))
        cache.get_or_load("key", lambda: "fresh", NOW, mark_stale=lambda value: value)

        result = cache.get_or_load(
            "key",
            lambda: (_ for _ in ()).throw(WeatherDataTimedOut()),
            NOW + timedelta(minutes=21),
            mark_stale=lambda value: f"stale:{value}",
        )

        self.assertEqual(result.value, "stale:fresh")
        self.assertTrue(result.stale)
        self.assertIsInstance(result.error, WeatherDataTimedOut)


class HeatInformationServiceTests(unittest.TestCase):
    def test_service_reuses_each_stream_for_twenty_minutes(self) -> None:
        class CountingWbgt:
            forecast_calls = 0
            observation_calls = 0

            def fetch_forecast(self, point_code, origin_at, retrieved_at):
                self.forecast_calls += 1
                return ()

            def fetch_observations(self, point_code, start_at, end_at, retrieved_at):
                self.observation_calls += 1
                return ()

        class CountingAlert:
            calls = 0

            def fetch_alerts(self, publication_url, target_date, retrieved_at, *, region_code=None):
                self.calls += 1
                return ()

        wbgt = CountingWbgt()
        alert = CountingAlert()
        service = OfficialHeatInformationService(wbgt, alert)
        arguments = {
            "point_code": "65042",
            "origin_at": NOW.replace(minute=0),
            "alert_publication_url": "https://example.test/alert.csv",
            "alert_target_date": NOW.date(),
            "region_code": "300000",
        }

        service.load(**arguments, now=NOW)
        service.load(**arguments, now=NOW + timedelta(minutes=19))

        self.assertEqual(wbgt.forecast_calls, 1)
        self.assertEqual(wbgt.observation_calls, 1)
        self.assertEqual(alert.calls, 1)

    def test_forecast_and_observation_have_distinct_freshness_limits(self) -> None:
        class OldWbgt:
            def fetch_forecast(self, point_code, origin_at, retrieved_at):
                return (
                    _reading(
                        WbgtValueKind.FORECAST,
                        reference_at=retrieved_at - timedelta(minutes=91),
                        valid_at=retrieved_at + timedelta(hours=1),
                    ),
                )

            def fetch_observations(self, point_code, start_at, end_at, retrieved_at):
                old = retrieved_at - timedelta(minutes=61)
                return (_reading(WbgtValueKind.ESTIMATED_ACTUAL, reference_at=old, valid_at=old),)

        class NoAlerts:
            def fetch_alerts(self, publication_url, target_date, retrieved_at, *, region_code=None):
                return ()

        result = OfficialHeatInformationService(OldWbgt(), NoAlerts()).load(
            point_code="65042",
            origin_at=NOW,
            alert_publication_url="https://example.test/alert.csv",
            alert_target_date=NOW.date(),
            now=NOW,
        )

        self.assertEqual([item.status for item in result.wbgt], [DataStatus.STALE, DataStatus.STALE])

    def test_external_failures_do_not_raise_or_block_route_layer(self) -> None:
        class BrokenWbgt:
            def fetch_forecast(self, point_code, origin_at, retrieved_at):
                raise WeatherDataTimedOut()

            def fetch_observations(self, point_code, start_at, end_at, retrieved_at):
                raise WeatherDataUnavailable()

        class BrokenAlert:
            def fetch_alerts(self, publication_url, target_date, retrieved_at, *, region_code=None):
                raise WeatherDataUnavailable()

        service = OfficialHeatInformationService(BrokenWbgt(), BrokenAlert())
        result = service.load(
            point_code="65042",
            origin_at=NOW,
            alert_publication_url="https://example.test/alert.csv",
            alert_target_date=NOW.date(),
            now=NOW,
            region_code="300000",
        )

        self.assertEqual(result.wbgt, ())
        self.assertEqual(result.alerts, ())
        self.assertEqual(len(result.problems), 3)
        self.assertTrue(all("経路検索は利用できます" in item for item in result.problems))


class RetryingTransportTests(unittest.TestCase):
    def test_rate_limit_is_retried_with_exponential_backoff(self) -> None:
        calls = []
        sleeps = []

        def rate_limited(url, timeout, user_agent):
            calls.append(url)
            raise HTTPError(url, 429, "limited", {}, None)

        transport = RetryingHttpTransport(
            attempts=3,
            backoff_seconds=0.1,
            opener=rate_limited,
            sleeper=sleeps.append,
        )
        with self.assertRaises(WeatherDataRateLimited):
            transport.get("https://example.test")

        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [0.1, 0.2])


def _reading(value_kind, *, reference_at, valid_at):
    return OfficialWbgtReading(
        source_id="test",
        source_url="https://example.test",
        point_code="65042",
        value_celsius=28.0,
        value_kind=value_kind,
        quality_code="test",
        reference_at=reference_at,
        valid_at=valid_at,
        retrieved_at=NOW,
    )


if __name__ == "__main__":
    unittest.main()
