import pytz
import math
import swisseph as swe
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views import View
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

# Import your untouched engine logic safely
from panchang_engine.engine import EphemerisComputationalEngine

# =====================================================================
# GLOBAL GEOLOCATION MIXIN (Shared Framework across Endpoint Classes)
# =====================================================================
class GeoLocationMixin:
    def __init__(self):
        self.geocoding_agent = Nominatim(user_agent="astrology_platform_agent")
        self.tz_finder = TimezoneFinder()
        
        # Absolute structural defaults: Ujjain, Madhya Pradesh, India
        self.DEFAULT_CITY = "Ujjain"
        self.DEFAULT_LAT = 23.1765
        self.DEFAULT_LON = 75.7885
        self.DEFAULT_TZ = "Asia/Kolkata"

    def resolve_location_and_tz(self, request):
        date_param = request.GET.get("date") or datetime.now().strftime("%Y-%m-%d")
        location_param = request.GET.get("location")

        try:
            now = datetime.now()
            parsed_date = datetime.strptime(date_param, "%Y-%m-%d")
            target_dt = parsed_date.replace(hour=now.hour, minute=now.minute, second=now.second)
        except ValueError:
            return None, None, None, None, None, None, None

        if location_param:
            try:
                geo_data = self.geocoding_agent.geocode(location_param, timeout=5)
                if geo_data:
                    lat, lon = geo_data.latitude, geo_data.longitude #type: ignore
                    resolved_location = location_param
                    tz_name = self.tz_finder.timezone_at(lng=lon, lat=lat) or self.DEFAULT_TZ
                else:
                    lat, lon, tz_name, resolved_location = self.DEFAULT_LAT, self.DEFAULT_LON, self.DEFAULT_TZ, self.DEFAULT_CITY
            except Exception:
                lat, lon, tz_name, resolved_location = self.DEFAULT_LAT, self.DEFAULT_LON, self.DEFAULT_TZ, self.DEFAULT_CITY
        else:
            lat, lon, tz_name, resolved_location = self.DEFAULT_LAT, self.DEFAULT_LON, self.DEFAULT_TZ, self.DEFAULT_CITY

        try:
            tz = pytz.timezone(tz_name)
            localized = tz.localize(target_dt)
            offset = localized.utcoffset()
            if offset is not None:
                numeric_tz = offset.total_seconds() / 3600.0
            else:
                numeric_tz = 5.5
        except Exception:
            numeric_tz = 5.5

        # 3. Pull Baseline Computations from Your Untouched Engine
        engine = EphemerisComputationalEngine()
        raw_metrics = engine.get_panchang_data(target_dt, lat, lon, tz_name)

        # 4. Generate Highly Dynamic Time Windows & Multi-Range Upto Elements
        def clean_time(time_val, default):
            if not time_val or time_val == "N/A": return default
            return time_val.replace(" AM", "").replace(" PM", "").strip()

        sunrise_str = clean_time(raw_metrics.get("sunrise"), "05:30")
        sunset_str = clean_time(raw_metrics.get("sunset"), "18:45")

        # --- Panchang Boundaries (Tithi, Nakshatra, Yoga, Karana) ---
        tithi_idx = int(elongation // 12) + 1
        if tithi_idx > 30: tithi_idx = 30
        tithi_end_jd = self._find_next_boundary(jd_now, swe.MOON, swe.SUN, 12, False, calc_flags)
        dt_tithi_end = jd_to_datetime(tithi_end_jd)

        nak_idx = int(moon_long // (360 / 27)) % 27
        nak_end_jd = self._find_next_boundary(jd_now, swe.MOON, None, 360/27, False, calc_flags)
        dt_nak_end = jd_to_datetime(nak_end_jd)

        yoga_idx = int(yoga_arc // (360 / 27)) % 27
        yoga_end_jd = self._find_next_boundary(jd_now, swe.MOON, swe.SUN, 360/27, True, calc_flags)
        dt_yoga_end = jd_to_datetime(yoga_end_jd)

        karana_idx = int(elongation // 6)
        karana_end_jd = self._find_next_boundary(jd_now, swe.MOON, swe.SUN, 6, False, calc_flags)
        dt_karana_end = jd_to_datetime(karana_end_jd)

        # Name mapping resolutions
        sun_sign = self.ZODIAC_SIGNS[int(sun_long // 30) % 12]
        moon_sign = self.ZODIAC_SIGNS[int(moon_long // 30) % 12]
        nakshatra_name = self.NAKSHATRAS[nak_idx]
        yoga_name = self.YOGAS[yoga_idx]
        next_yoga_name = self.YOGAS[(yoga_idx + 1) % 27]

        if karana_idx == 0:
            karana_name = self.KARANAS[0]
        elif karana_idx >= 57:
            karana_name = self.KARANAS[karana_idx - 49]
        else:
            karana_name = self.KARANAS[((karana_idx - 1) % 7) + 1]

        TITHI_LABELS = [
            "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shasthi", "Saptami", "Ashtami", 
            "Navami", "Dashami", "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi", "Purnima",
            "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shasthi", "Saptami", "Ashtami", 
            "Navami", "Dashami", "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi", "Amavasya"
        ]
        paksha_name, paksha_label = ("Shukla", "Waxing Moon") if elongation < 180 else ("Krishna", "Waning Moon")
        MONTHS_POOL = ["Chaitra", "Vaisakha", "Jyaistha", "Asadha", "Sravana", "Bhadrapada", "Asvina", "Kartika", "Margasirsa", "Pausa", "Magha", "Phalguna"]

        # --- Dynamic Horizon Calculations ---
        # Note: pyswisseph takes longitude before latitude, and tracks atmospheric refraction by default.
        horizon_flags = swe.BIT_DISC_CENTER
        
        # Sun Horizon calculations
        try:
            sunrise_jd = swe.rise_trans(jd_local_midnight, swe.SUN, horizon_flags, lon, lat, 0, 0, 0, swe.CALC_RISE)[1][0]
            sunset_jd = swe.rise_trans(jd_local_midnight, swe.SUN, horizon_flags, lon, lat, 0, 0, 0, swe.CALC_SET)[1][0]
        except (TypeError, IndexError, swe.Error):
            sunrise_jd = jd_local_midnight + (5.38 / 24.0)
            sunset_jd = jd_local_midnight + (19.51 / 24.0)

        # Moon Horizon calculations with 0.5-day tracking offset logic to widen operational capture boundaries
        try:
            moonrise_jd = swe.rise_trans(jd_local_midnight - 0.5, swe.MOON, horizon_flags, lon, lat, 0, 0, 0, swe.CALC_RISE)[1][0]
            if moonrise_jd < jd_local_midnight:
                moonrise_jd = swe.rise_trans(jd_local_midnight, swe.MOON, horizon_flags, lon, lat, 0, 0, 0, swe.CALC_RISE)[1][0]
        except (TypeError, IndexError, swe.Error):
            moonrise_jd = jd_local_midnight + (6.31 / 24.0)

        try:
            moonset_jd = swe.rise_trans(jd_local_midnight - 0.5, swe.MOON, horizon_flags, lon, lat, 0, 0, 0, swe.CALC_SET)[1][0]
            if moonset_jd < jd_local_midnight:
                moonset_jd = swe.rise_trans(jd_local_midnight, swe.MOON, horizon_flags, lon, lat, 0, 0, 0, swe.CALC_SET)[1][0]
        except (TypeError, IndexError, swe.Error):
            moonset_jd = jd_local_midnight + (21.1 / 24.0)

        return {
            "sunrise": jd_to_datetime(sunrise_jd),
            "sunset": jd_to_datetime(sunset_jd),
            "moonrise": jd_to_datetime(moonrise_jd),
            "moonset": jd_to_datetime(moonset_jd),
            "sun_sign": sun_sign,
            "moon_sign": moon_sign,
            "tithi_name": f"{paksha_name} {TITHI_LABELS[tithi_idx - 1]}",
            "tithi_upto": dt_tithi_end,
            "nakshatra_name": nakshatra_name,
            "nakshatra_upto": dt_nak_end,
            "yoga_name": yoga_name,
            "yoga_upto": dt_yoga_end,
            "next_yoga": next_yoga_name,
            "karana_name": karana_name,
            "karana_upto": dt_karana_end,
            "paksha_name": paksha_name,
            "paksha_label": paksha_label,
            "amanta": MONTHS_POOL[int(sun_long // 30) % 12],
            "purnima": MONTHS_POOL[(int(sun_long // 30) + 1) % 12],
            "pravishte_val": int(math.floor(sun_long % 30)) + 1,
            "pravishte_lbl": TITHI_LABELS[(int(math.floor(sun_long % 30))) % 15]
        }

    def get(self, request, *args, **kwargs):
        geo_data = self.resolve_location_and_tz(request)
        if not geo_data[0]:
            return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)
            
        date_param, target_dt, resolved_location, tz_name, numeric_tz, lat, lon = geo_data

        # Compute dynamic metrics directly from the core ephemeris engine
        astro = self._calculate_panchang_metrics(target_dt, numeric_tz, lat, lon)

        # Dynamic Muhurat ranges derived directly from actual sunrise/sunset timings
        day_length_sec = (astro["sunset"] - astro["sunrise"]).total_seconds()
        part_duration = day_length_sec / 8

        def make_range_string(base_time: datetime, offset_sec: float, duration_sec: float) -> str:
            start = base_time + timedelta(seconds=offset_sec)
            end = start + timedelta(seconds=duration_sec)
            return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"

        abhijit_range = make_range_string(astro["sunrise"], (day_length_sec / 2) - 1440, 2880)
        rahu_parts_mapping = {0: 1, 1: 6, 2: 4, 3: 5, 4: 3, 5: 2, 6: 7}
        rahu_range = make_range_string(astro["sunrise"], part_duration * rahu_parts_mapping.get(target_dt.weekday(), 1), part_duration)

        # Dynamic Era Calendars calculation
        shaka_year = target_dt.year - 78 if target_dt.month > 3 else target_dt.year - 79
        vikram_year = target_dt.year + 57 if target_dt.month > 3 else target_dt.year + 56

        # Array indexing for looking up sequential Yoga patterns dynamically
        YOGAS_SEQUENCE = [
            "Vishkumbha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda", "Sukarma", 
            "Dhriti", "Shula", "Ganda", "Vridhi", "Dhruva", "Vyaghata", "Harshana", "Vajra", 
            "Siddhi", "Vyatipata", "Variyan", "Parigha", "Shiva", "Siddha", "Sadhya", "Shubha", 
            "Shukla", "Brahma", "Indra", "Vaidhriti"
        ]
        WEEKDAY_LORDS = {
            "Monday": "Moon", "Tuesday": "Mars", "Wednesday": "Mercury", 
            "Thursday": "Jupiter", "Friday": "Venus", "Saturday": "Saturn", "Sunday": "Sun"
        }

        current_yoga_clean = str(raw_metrics.get("yoga", "Siddha")).strip().capitalize()
        try:
            next_yoga = YOGAS_SEQUENCE[(YOGAS_SEQUENCE.index(current_yoga_clean) + 1) % len(YOGAS_SEQUENCE)]
        except ValueError:
            next_yoga = "Sadhya"

        resolved_vara = str(raw_metrics.get("vara", target_dt.strftime("%A"))).strip().capitalize()

        # 6. Build the Final Schema Payload Map
        payload = {
            "date": date_param,
            "location": resolved_location,
            "panchang": {
                "sunrise": astro["sunrise"].strftime("%H:%M"),
                "abhijeet_moohrat": abhijit_range,
                "rahukal": rahu_range,
                "sunset": dt_sunset.strftime("%H:%M"),
                "moonrise": dt_moonrise.strftime("%H:%M"),
                "moonset": dt_moonset.strftime("%H:%M"),
                "moon_sign": raw_metrics.get("moon_sign", "Unknown"),
                "sun_sign": raw_metrics.get("sun_sign", "Unknown"),
                "shaka_samvat": str(shaka_year),
                "vikram_samvat": str(vikram_year),
                "tithi": {
                    "name": lunar_meta["tithi_name"],
                    "upto": tithi_upto
                },
                "nakshatra": {
                    "name": raw_metrics.get("nakshatra", "Unknown"),
                    "upto": nakshatra_upto
                },
                "yoga": {
                    "name": current_yoga_clean,
                    "upto": yoga_upto,
                    "next": next_yoga
                },
                "karana": {
                    "name": raw_metrics.get("karana", "Unknown"),
                    "upto": karana_upto
                },
                "var": {
                    "name": resolved_vara,
                    "ruler": WEEKDAY_LORDS.get(resolved_vara, "Sun")
                },
                "paksha": {
                    "name": lunar_meta["paksha_name"],
                    "label": lunar_meta["paksha_label"]
                },
                "amanta_month": {
                    "name": lunar_meta["amanta"],
                    "note": "Lunar month"
                },
                "purnima_month": {
                    "name": lunar_meta["purnima"],
                    "note": "Lunar month"
                },
                "pravishte_gate": {
                    "value": lunar_meta["pravishte_val"],
                    "label": lunar_meta["pravishte_lbl"]
                }
            }
        }
        
        return JsonResponse(payload, json_dumps_params={'indent': 2})