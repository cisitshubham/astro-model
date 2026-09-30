from datetime import datetime as real_datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytz
from django.test import RequestFactory, SimpleTestCase

from panchang_engine.views import GeoLocationMixin, GlobalPanchangAPIView


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

