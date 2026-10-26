from datetime import datetime, timezone
from unittest import TestCase, mock

from django.test import SimpleTestCase

from . import providers, service
from .risk import HIGH, LOW, MODERATE, NO_TRAVEL, SEVERE, classify


class ClassifyTests(TestCase):
    def level(self, wind=0, rain=0, snow=0, load=10_000):
        return classify(wind, rain, snow, load)["level"]

    def test_calm_weather_is_low(self):
        self.assertEqual(self.level(), LOW)

    def test_wind_bands(self):
        self.assertEqual(self.level(wind=24.9), LOW)
        self.assertEqual(self.level(wind=25), MODERATE)
        self.assertEqual(self.level(wind=35), HIGH)
        self.assertEqual(self.level(wind=45), SEVERE)
        self.assertEqual(self.level(wind=55), NO_TRAVEL)

    def test_rain_bands_and_strict_no_travel(self):
        self.assertEqual(self.level(rain=0.10), MODERATE)
        self.assertEqual(self.level(rain=0.25), HIGH)
        self.assertEqual(self.level(rain=0.50), SEVERE)
        self.assertEqual(self.level(rain=1.00), SEVERE)  # "> 1.00" is No Travel
        self.assertEqual(self.level(rain=1.01), NO_TRAVEL)

    def test_snow_bands_and_strict_no_travel(self):
        self.assertEqual(self.level(snow=0.5), MODERATE)
        self.assertEqual(self.level(snow=1.0), HIGH)
        self.assertEqual(self.level(snow=2.0), SEVERE)
        self.assertEqual(self.level(snow=3.0), SEVERE)
        self.assertEqual(self.level(snow=3.1), NO_TRAVEL)

    def test_worst_factor_wins(self):
        self.assertEqual(self.level(wind=26, rain=0.3, snow=0.6), HIGH)

    def test_heavy_load_in_severe_wind_is_no_travel(self):
        self.assertEqual(self.level(wind=45, load=30_000), SEVERE)
        self.assertEqual(self.level(wind=45, load=30_001), NO_TRAVEL)
        self.assertEqual(self.level(wind=54, load=50_000), NO_TRAVEL)

    def test_heavy_load_in_high_wind_is_severe(self):
        self.assertEqual(self.level(wind=35, load=40_000), HIGH)
        self.assertEqual(self.level(wind=35, load=40_001), SEVERE)
        self.assertEqual(self.level(wind=44, load=60_000), SEVERE)

    def test_load_rule_never_lowers_a_worse_level(self):
        self.assertEqual(self.level(wind=40, rain=2.0, load=60_000), NO_TRAVEL)

    def test_no_travel_wind_applies_to_any_load(self):
        self.assertEqual(self.level(wind=55, load=0), NO_TRAVEL)


class CheckpointTests(TestCase):
    coords = [(40.0, -100.0), (40.0, -99.0), (40.0, -98.0)]  # ~85 miles due east

    def test_includes_both_ends_and_covers_whole_route(self):
        total_m = 85 * 1609.344
        cps = service.build_checkpoints(self.coords, total_m, 3600 * 2, 25)
        self.assertEqual(cps[0]["mile"], 0)
        self.assertAlmostEqual(cps[-1]["mile"], 85, places=1)
        self.assertEqual([round(c["mile"]) for c in cps[:4]], [0, 25, 50, 75])
        self.assertAlmostEqual(sum(c["segment_mi"] for c in cps), 85, places=6)

    def test_eta_scales_with_distance(self):
        cps = service.build_checkpoints(self.coords, 85 * 1609.344, 7200, 25)
        self.assertAlmostEqual(cps[-1]["seconds"], 7200)
        self.assertAlmostEqual(cps[1]["seconds"], 7200 * 25 / 85)


def _route(label, no_travel=0.0, severe=0.0, high=0.0, avg=0.0, hours=5.0):
    return {
        "id": label,
        "label": f"Route {label}",
        "duration_h": hours,
        "summary": {
            "miles_by_level": {
                "Low": 0, "Moderate": 0, "High": high, "Severe": severe, "No Travel": no_travel,
            },
            "avg_risk": avg,
        },
    }


class RankingTests(TestCase):
    def test_fewest_severe_miles_beats_speed(self):
        routes = [_route("A", severe=10, hours=4), _route("B", severe=2, hours=7)]
        service.rank_routes(routes)
        self.assertEqual([r["id"] for r in routes], ["B", "A"])

    def test_high_miles_break_a_severe_tie(self):
        routes = [_route("A", high=30), _route("B", high=5)]
        service.rank_routes(routes)
        self.assertEqual(routes[0]["id"], "B")

    def test_avg_risk_then_time_break_later_ties(self):
        routes = [_route("A", avg=1.2, hours=3), _route("B", avg=0.8, hours=6)]
        service.rank_routes(routes)
        self.assertEqual(routes[0]["id"], "B")
        routes = [_route("A", avg=0.5, hours=6), _route("B", avg=0.5, hours=4)]
        service.rank_routes(routes)
        self.assertEqual(routes[0]["id"], "B")

    def test_no_travel_is_worse_than_severe(self):
        routes = [_route("A", no_travel=5), _route("B", severe=50)]
        service.rank_routes(routes)
        self.assertEqual(routes[0]["id"], "B")

    def test_reason_names_the_deciding_criterion(self):
        routes = [_route("A", severe=10), _route("B", severe=2)]
        reason = service.rank_routes(routes)
        self.assertIn("Severe miles", reason)
        self.assertEqual([r["rank"] for r in routes], [1, 2])


class EvaluateRouteTests(TestCase):
    def test_miles_and_risk_come_from_eta_weather(self):
        departure = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
        start = datetime(2026, 10, 26, tzinfo=timezone.utc)  # series starts at 00:00
        hours = 24 * 5
        # Calm everywhere, except a 50 mph gust at hour 40 (2026-10-27 16:00 UTC).
        wind = [10.0] * hours
        wind[40] = 50.0
        series = {"start": start, "wind": wind, "rain": [0.0] * hours, "snow": [0.0] * hours}
        route = {
            "coords": [(40.0, -100.0), (40.0, -98.0)],
            "distance_m": 100 * 1609.344,
            "duration_s": 4 * 3600,  # arrives 16:00, the gust hour
        }
        weather = {(40.0, -100.0): series, (40.0, -99.0): series, (40.0, -98.0): series}
        result = service.evaluate_route(route, "A", departure, 35_000, 50, weather)
        self.assertEqual([p["level_name"] for p in result["checkpoints"]], ["Low", "Low", "No Travel"])
        self.assertAlmostEqual(result["summary"]["miles_by_level"]["No Travel"], 25.0, places=1)
        self.assertEqual(len(result["checkpoints"][0]["forecast"]["level"]), 49)


class ValidationTests(SimpleTestCase):
    def test_rejects_bad_interval(self):
        with self.assertRaises(service.PlanError):
            service.plan_trip({
                "origin": "a", "destination": "b", "load_lb": 1000,
                "interval_mi": 7, "departure": "2030-01-01T00:00:00Z",
            })

    def test_rejects_past_departure(self):
        now = datetime(2026, 10, 27, tzinfo=timezone.utc)
        with self.assertRaises(service.PlanError):
            service.plan_trip({
                "origin": "a", "destination": "b", "load_lb": 1000,
                "interval_mi": 25, "departure": "2026-10-20T00:00:00Z",
            }, now=now)

    def test_api_returns_json_error(self):
        response = self.client.post("/api/plan", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())


class GeocodeFallbackTests(TestCase):
    def setUp(self):
        providers._geocode_cache.clear()

    def test_falls_through_to_next_geocoder_on_error(self):
        import requests

        def broken(query):
            raise requests.HTTPError("429 Too Many Requests")

        fallback = mock.Mock(return_value=(1.0, 2.0, "Somewhere"))
        with mock.patch.object(providers, "GEOCODERS", (broken, fallback)):
            self.assertEqual(providers.geocode("Somewhere"), (1.0, 2.0, "Somewhere"))

    def test_not_found_is_a_client_error(self):
        with mock.patch.object(providers, "GEOCODERS", (lambda q: None,)):
            with self.assertRaises(providers.ProviderError) as ctx:
                providers.geocode("Nowhere at all")
        self.assertEqual(ctx.exception.status, 400)

    def test_coordinates_skip_geocoding(self):
        self.assertEqual(providers.geocode("40.5, -100.25")[:2], (40.5, -100.25))


class MetNorwayTests(TestCase):
    def _response(self, timeseries):
        resp = mock.Mock()
        resp.json.return_value = {"properties": {"timeseries": timeseries}}
        resp.raise_for_status.return_value = None
        return resp

    def test_expands_six_hour_steps_and_splits_snow_by_temperature(self):
        timeseries = [
            {"time": "2026-10-27T00:00:00Z", "data": {
                "instant": {"details": {"wind_speed": 10.0, "air_temperature": 5.0}},
                "next_1_hours": {"details": {"precipitation_amount": 2.54}}}},
            {"time": "2026-10-27T01:00:00Z", "data": {
                "instant": {"details": {"wind_speed": 20.0, "air_temperature": -3.0}},
                "next_6_hours": {"details": {"precipitation_amount": 15.24}}}},
            {"time": "2026-10-27T07:00:00Z", "data": {
                "instant": {"details": {"wind_speed": 0.0, "air_temperature": 2.0}}}},
        ]
        with mock.patch.object(providers._session, "get", return_value=self._response(timeseries)):
            series = providers._met_point((40.0, -100.0))
        self.assertEqual(len(series["wind"]), 8)
        self.assertAlmostEqual(series["rain"][0], 0.1)  # 2.54 mm in one hour
        self.assertAlmostEqual(series["wind"][0], 22.37, places=2)
        # 15.24 mm over 6 freezing hours = 0.1 in/hr liquid = 1.0 in/hr of snow.
        self.assertAlmostEqual(series["snow"][3], 1.0)
        self.assertEqual(series["rain"][3], 0.0)
        self.assertEqual(series["rain"][7], 0.0)

    def test_switches_to_met_after_open_meteo_rate_limit(self):
        providers._open_meteo_paused_until = 0.0
        met = {"start": None, "wind": [0.0], "rain": [0.0], "snow": [0.0]}
        with mock.patch.object(providers, "_open_meteo_batch", side_effect=providers.RateLimited("429")), \
                mock.patch.object(providers, "_met_point", return_value=met) as met_point:
            fetched = providers._fetch([(1.0, 2.0), (3.0, 4.0)], 3)
        self.assertEqual(met_point.call_count, 2)
        self.assertEqual(set(fetched), {(1.0, 2.0), (3.0, 4.0)})
        self.assertGreater(providers._open_meteo_paused_until, 0)
        providers._open_meteo_paused_until = 0.0
