from datetime import datetime as real_datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytz
from django.test import RequestFactory, SimpleTestCase

from panchang_engine.views import (
    GeoLocationMixin,
    GlobalCelestialAPIView,
    GlobalMoohratsAPIView,
    GlobalPanchangAPIView,
    GlobalTransitsAPIView,
)


class FixedDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        fixed_utc = real_datetime(2026, 9, 30, 20, 0, tzinfo=pytz.UTC)
        return fixed_utc.astimezone(tz) if tz else fixed_utc.replace(tzinfo=None)


class GeoLocationMixinTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.resolver = GeoLocationMixin()
        self.resolver.geocoding_agent = Mock()
        self.resolver.tz_finder = Mock()

    @patch("panchang_engine.views.cache.get", return_value=None)
    @patch("panchang_engine.views.cache.set")
    @patch("panchang_engine.views.datetime", FixedDateTime)
    def test_city_is_geocoded_inside_engine_and_uses_city_local_today(
        self, _cache_set, _cache_get
    ):
        self.resolver.geocoding_agent.geocode.return_value = SimpleNamespace(
            latitude=40.7128,
            longitude=-74.0060,
        )
        self.resolver.tz_finder.timezone_at.return_value = "America/New_York"

        result = self.resolver.resolve_location_and_tz(
            self.factory.get("/api/panchang/", {"city": "New York"})
        )

        date_param, _, location, timezone, _, lat, lon = result
        self.assertEqual(date_param, "2026-09-30")
        self.assertEqual(location, "New York")
        self.assertEqual(timezone, "America/New_York")
        self.assertEqual((lat, lon), (40.7128, -74.0060))
        self.resolver.geocoding_agent.geocode.assert_called_once_with(
            "New York", timeout=5
        )

    @patch("panchang_engine.views.cache.get", return_value=None)
    @patch("panchang_engine.views.datetime", FixedDateTime)
    def test_unresolved_city_falls_back_to_ujjain(self, _cache_get):
        self.resolver.geocoding_agent.geocode.return_value = None

        result = self.resolver.resolve_location_and_tz(
            self.factory.get("/api/panchang/", {"city": "Unknown City"})
        )

        date_param, _, location, timezone, offset, lat, lon = result
        self.assertEqual(date_param, "2026-10-01")
        self.assertEqual(location, "Ujjain")
        self.assertEqual(timezone, "Asia/Kolkata")
        self.assertEqual(offset, 5.5)
        self.assertEqual((lat, lon), (23.1765, 75.7885))

    @patch("panchang_engine.views.datetime", FixedDateTime)
    def test_existing_location_parameter_remains_supported(self):
        self.resolver.geocoding_agent.geocode.return_value = SimpleNamespace(
            latitude=28.6139,
            longitude=77.2090,
        )
        self.resolver.tz_finder.timezone_at.return_value = "Asia/Kolkata"

        with patch("panchang_engine.views.cache.get", return_value=None), patch(
            "panchang_engine.views.cache.set"
        ):
            result = self.resolver.resolve_location_and_tz(
                self.factory.get(
                    "/api/panchang/",
                    {"location": "New Delhi", "date": "2026-09-30"},
                )
            )

        self.assertEqual(result[0], "2026-09-30")
        self.assertEqual(result[2], "New Delhi")


class PanchangResponseContractTests(SimpleTestCase):
    @patch.object(GlobalPanchangAPIView, "_calculate_panchang_metrics")
    def test_city_support_does_not_add_or_remove_response_fields(self, calculate):
        base = real_datetime(2026, 9, 30, 12, 0)
        calculate.return_value = {
            "sunrise": base.replace(hour=6),
            "sunset": base.replace(hour=18),
            "moonrise": base.replace(hour=20),
            "moonset": base.replace(hour=8),
            "moon_sign": "Aries",
            "sun_sign": "Virgo",
            "tithi_name": "Krishna Panchami",
            "tithi_upto": base.replace(hour=14),
            "nakshatra_name": "Bharani",
            "nakshatra_upto": base.replace(hour=15),
            "yoga_name": "Vajra",
            "yoga_upto": base.replace(hour=16),
            "next_yoga": "Siddhi",
            "karana_name": "Balava",
            "karana_upto": base.replace(hour=17),
            "paksha_name": "Krishna",
            "paksha_label": "Waning Moon",
            "amanta": "Bhadrapada",
            "purnima": "Asvina",
            "pravishte_val": 14,
            "pravishte_lbl": "Chaturdashi",
        }

        response = self.client.get(
            "/api/panchang/", {"date": "2026-09-30"}
        )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(payload), {"date", "location", "panchang"})
        self.assertEqual(payload["panchang"]["abhijeet_moohrat"], "-")
        self.assertEqual(
            set(payload["panchang"]),
            {
                "sunrise",
                "abhijeet_moohrat",
                "rahukal",
                "overLap",
                "sunset",
                "moonrise",
                "moonset",
                "moon_sign",
                "sun_sign",
                "shaka_samvat",
                "vikram_samvat",
                "tithi",
                "nakshatra",
                "yoga",
                "karana",
                "var",
                "paksha",
                "amanta_month",
                "purnima_month",
                "pravishte_gate",
            },
        )


class LocationAwareEndpointTests(SimpleTestCase):
    def test_transits_use_the_resolved_city_timezone_for_the_local_day(self):
        resolved = (
            "2026-07-01",
            real_datetime(2026, 7, 1, 12, 0),
            "New York",
            "America/New_York",
            -4.0,
            40.7128,
            -74.0060,
        )

        with patch.object(
            GlobalTransitsAPIView,
            "resolve_location_and_tz",
            return_value=resolved,
        ), patch("panchang_engine.views.swe.julday", return_value=2461223.5) as julday, patch(
            "panchang_engine.views.swe.calc_ut",
            return_value=([10.0, 0.0, 0.0, 0.1], 0),
        ):
            response = self.client.get(
                "/api/transits/",
                {"date": "2026-07-01", "location": "New York"},
            )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(payload), {"date", "location", "transits"})
        self.assertEqual(payload["location"], "New York")
        # Midnight in New York during DST is 04:00 UTC.
        self.assertEqual(julday.call_args_list[0].args[3], 4.0)

    def test_positions_alias_uses_resolved_coordinates_topocentrically(self):
        resolved = (
            "2026-07-01",
            real_datetime(2026, 7, 1, 12, 0),
            "New York",
            "America/New_York",
            -4.0,
            40.7128,
            -74.0060,
        )

        with patch.object(
            GlobalCelestialAPIView,
            "resolve_location_and_tz",
            return_value=resolved,
        ), patch("panchang_engine.views.swe.set_topo") as set_topo, patch(
            "panchang_engine.views.swe.calc_ut",
            return_value=([45.0, 0.0, 0.0, 0.1], 0),
        ) as calc_ut:
            response = self.client.get(
                "/api/positions/",
                {"date": "2026-07-01", "location": "New York"},
            )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(payload), {"date", "location", "positions"})
        self.assertEqual(payload["location"], "New York")
        set_topo.assert_called_once_with(-74.0060, 40.7128, 0.0)
        self.assertTrue(
            all(call.args[2] & __import__("swisseph").FLG_TOPOCTR for call in calc_ut.call_args_list)
        )

    def test_moohrats_use_city_coordinates_and_each_days_dst_offset(self):
        resolved = (
            "2026-03-01",
            real_datetime(2026, 3, 1, 12, 0),
            "New York",
            "America/New_York",
            -5.0,
            40.7128,
            -74.0060,
        )

        def fixed_sunrise_sunset(target_date, _lat, _lon, _offset):
            return target_date.replace(hour=6), target_date.replace(hour=18)

        with patch.object(
            GlobalMoohratsAPIView,
            "resolve_location_and_tz",
            return_value=resolved,
        ) as resolver, patch.object(
            GlobalMoohratsAPIView,
            "_get_sunrise_sunset",
            side_effect=fixed_sunrise_sunset,
        ) as sunrise_sunset, patch(
            "panchang_engine.views.swe.calc_ut",
            return_value=([10.0, 0.0, 0.0, 0.1], 0),
        ):
            response = self.client.get(
                "/api/moohrats/",
                {
                    "month": "March",
                    "year": "2026",
                    "location": "New York",
                    "title": "vivahmuhurat",
                },
            )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(payload), {"moohrats"})
        self.assertEqual(
            resolver.call_args.kwargs["date_override"],
            "2026-03-01",
        )
        offsets = {call.args[3] for call in sunrise_sunset.call_args_list}
        self.assertEqual(offsets, {-5.0, -4.0})
        self.assertTrue(
            all(
                call.args[1:3] == (40.7128, -74.0060)
                for call in sunrise_sunset.call_args_list
            )
        )

