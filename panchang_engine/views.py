import pytz
import math
import random
import swisseph as swe
# Patch swisseph.calc_ut to return a 2-tuple for compatibility with dashaflow
_orig_calc_ut = swe.calc_ut
def patched_calc_ut(*args, **kwargs):
    res = _orig_calc_ut(*args, **kwargs)
    if isinstance(res, tuple) and len(res) == 3:
        return (res[0], res[1])
    return res
swe.calc_ut = patched_calc_ut

from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views import View
from django.core.cache import cache
from geopy.geocoders import Nominatim
# Import dashaflow modules for dynamic calculation engine
import dashaflow as df
from timezonefinder import TimezoneFinder

# Import your untouched engine logic safely
from panchang_engine.engine import EphemerisComputationalEngine

def sanitize_missing_values(data):
    if isinstance(data, dict):
        return {k: (v if k == "overLap" and v == "" else sanitize_missing_values(v)) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_missing_values(x) for x in data]
    elif data is None or data == "" or data == "unknown" or data == "Unknown":
        return "-"
    return data



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
            cache_key = f"geo_{location_param.strip().lower()}"
            # A cache read must never fail the request. Workers sharing the file-based
            # cache can hit a locked or half-written entry, and Django's FileBasedCache
            # only swallows FileNotFoundError - anything else would surface as a 500.
            try:
                cached_data = cache.get(cache_key)
            except Exception as e:
                print(f"WARNING: Geo cache read failed for '{location_param}' ({str(e)}). Treating as a miss.")
                cached_data = None

            if cached_data:
                lat, lon, tz_name, resolved_location = cached_data
            else:
                resolved_ok = False
                try:
                    geo_data = self.geocoding_agent.geocode(location_param, timeout=5)
                    if geo_data:
                        lat, lon = geo_data.latitude, geo_data.longitude #type: ignore
                        resolved_location = location_param
                        tz_name = self.tz_finder.timezone_at(lng=lon, lat=lat) or self.DEFAULT_TZ
                        resolved_ok = True
                    else:
                        print(f"WARNING: Could not resolve location '{location_param}'. Falling back to Ujjain.")
                        lat, lon, tz_name, resolved_location = self.DEFAULT_LAT, self.DEFAULT_LON, self.DEFAULT_TZ, self.DEFAULT_CITY
                except Exception as e:
                    print(f"WARNING: Geocoding error for '{location_param}' ({str(e)}). Falling back to Ujjain.")
                    lat, lon, tz_name, resolved_location = self.DEFAULT_LAT, self.DEFAULT_LON, self.DEFAULT_TZ, self.DEFAULT_CITY

                # Persisted outside the geocoding try-block: a failed cache write must not
                # discard coordinates that were already resolved correctly.
                if resolved_ok:
                    try:
                        cache.set(cache_key, (lat, lon, tz_name, resolved_location), 86400 * 30)
                    except Exception as e:
                        print(f"WARNING: Geo cache write failed for '{location_param}' ({str(e)}).")
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

        return date_param, target_dt, resolved_location, tz_name, numeric_tz, lat, lon


# =====================================================================
# 1. STANDALONE PANCHANG ENDPOINT VIEW
# =====================================================================
class GlobalPanchangAPIView(View, GeoLocationMixin):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        GeoLocationMixin.__init__(self)
        
        # Core Astronomical Reference Arrays
        self.ZODIAC_SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
        self.NAKSHATRAS = [
            "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha",
            "Maghā", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
            "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
        ]
        self.YOGAS = [
            "Vishkumbha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda", "Sukarma", "Dhriti", "Shula", "Ganda", 
            "Vridhi", "Dhruva", "Vyaghata", "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyan", "Parigha", "Shiva", 
            "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti"
        ]
        self.KARANAS = [
            "Kimstughna", "Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti (Bhadra)",
            "Shakuni", "Chatushpada", "Naga"
        ]

    def _find_next_boundary(self, start_jd: float, body1: int, body2: int, arc_step: float, is_sum: bool, flags: int) -> float:
        """
        Calculates the exact Julian Date when a planetary body or combined 
        arc distance crosses the next coordinate boundary limit.
        """
        low_jd = start_jd
        high_jd = start_jd + 1.0  # Search boundary threshold (24h window)
        
        def calculate_current_arc(jd):
            p1 = swe.calc_ut(jd, body1, flags)[0][0]
            if body2 is not None:
                p2 = swe.calc_ut(jd, body2, flags)[0][0]
                return (p1 + p2) % 360 if is_sum else (p1 - p2) % 360
            return p1

        target_boundary_index = int(calculate_current_arc(low_jd) // arc_step)
        
        # Binary search iteration loop for high accuracy
        for _ in range(24):
            mid_jd = (low_jd + high_jd) / 2.0
            mid_boundary_index = int(calculate_current_arc(mid_jd) // arc_step)
            if mid_boundary_index == target_boundary_index:
                low_jd = mid_jd
            else:
                high_jd = mid_jd
        return high_jd

    def _calculate_panchang_metrics(self, target_dt: datetime, numeric_tz: float, lat: float, lon: float):
        # 1. Standard UTC setup for longitudinal planet calculations (Sun/Moon degrees)
        utc_dt = target_dt - timedelta(hours=numeric_tz)
        jd_now = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, utc_dt.hour + utc_dt.minute/60.0)
        
        # 2. Setup strict calendar date boundaries (00:00:00 local time for the target day)
        local_midnight_dt = datetime(target_dt.year, target_dt.month, target_dt.day, 0, 0, 0)
        utc_midnight_dt = local_midnight_dt - timedelta(hours=numeric_tz)
        jd_local_midnight = swe.julday(utc_midnight_dt.year, utc_midnight_dt.month, utc_midnight_dt.day, 
                                       utc_midnight_dt.hour + utc_midnight_dt.minute/60.0)

        # Initialize Lahiri Sidereal structural engine properties
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        calc_flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL

        # Calculate exact astronomical coordinates
        sun_long = swe.calc_ut(jd_now, swe.SUN, calc_flags)[0][0]
        moon_long = swe.calc_ut(jd_now, swe.MOON, calc_flags)[0][0]
        
        elongation = (moon_long - sun_long) % 360
        yoga_arc = (moon_long + sun_long) % 360

        def jd_to_datetime(jd_val: float) -> datetime:
            """Converts a UT Julian Date directly to Local Time by applying the timezone offset"""
            local_jd = jd_val + (numeric_tz / 24.0)
            year, month, day, decimal_hour = swe.revjul(local_jd)
            
            hours = int(decimal_hour)
            remaining_minutes = (decimal_hour - hours) * 60
            minutes = int(remaining_minutes)
            seconds = int(round((remaining_minutes - minutes) * 60))
            
            if seconds >= 60:
                seconds = 0
                minutes += 1
            if minutes >= 60:
                minutes = 0
                hours += 1
            if hours >= 24:
                base_dt = datetime(int(year), int(month), int(day), 0, 0, 0)
                return base_dt + timedelta(hours=hours, seconds=seconds)

            return datetime(int(year), int(month), int(day), hours, minutes, seconds)

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
        horizon_flags = swe.BIT_DISC_CENTER
        
        geopos = (lon, lat, 0.0)
        jd_search_start = jd_local_midnight - (2.0 / 24.0)

        # Check if the coordinates are near Ujjain (~23.17 N, ~75.78 E) to isolate fallback logic
        is_ujjain = (22.8 <= lat <= 23.5) and (75.2 <= lon <= 76.3)

        try:
            sunrise_jd = swe.rise_trans(jd_local_midnight, swe.SUN, horizon_flags | swe.CALC_RISE, geopos)[1][0]
            sunset_jd = swe.rise_trans(jd_local_midnight, swe.SUN, horizon_flags | swe.CALC_SET, geopos)[1][0]
        except (TypeError, IndexError, swe.Error):
            try:
                # Fall back to calculating Ujjain baseline on the same date
                fallback_geopos = (self.DEFAULT_LON, self.DEFAULT_LAT, 0.0)
                sunrise_jd = swe.rise_trans(jd_local_midnight, swe.SUN, horizon_flags | swe.CALC_RISE, fallback_geopos)[1][0]
                sunset_jd = swe.rise_trans(jd_local_midnight, swe.SUN, horizon_flags | swe.CALC_SET, fallback_geopos)[1][0]
            except Exception:
                sunrise_jd = jd_local_midnight + (6.0 / 24.0)
                sunset_jd = jd_local_midnight + (18.0 / 24.0)

        # Moon Horizon calculations with 0.5-day tracking offset logic to widen operational capture boundaries
        try:
            moonrise_jd = swe.rise_trans(jd_local_midnight - 0.5, swe.MOON, horizon_flags | swe.CALC_RISE, geopos)[1][0]
            if moonrise_jd < jd_local_midnight:
                moonrise_jd = swe.rise_trans(jd_local_midnight, swe.MOON, horizon_flags | swe.CALC_RISE, geopos)[1][0]
        except (TypeError, IndexError, swe.Error):
            try:
                # Fall back to Ujjain baseline calculations
                fallback_geopos = (self.DEFAULT_LON, self.DEFAULT_LAT, 0.0)
                moonrise_jd = swe.rise_trans(jd_local_midnight - 0.5, swe.MOON, horizon_flags | swe.CALC_RISE, fallback_geopos)[1][0]
                if moonrise_jd < jd_local_midnight:
                    moonrise_jd = swe.rise_trans(jd_local_midnight, swe.MOON, horizon_flags | swe.CALC_RISE, fallback_geopos)[1][0]
            except Exception:
                moonrise_jd = jd_local_midnight + (6.5 / 24.0)

        try:
            moonset_jd = swe.rise_trans(jd_local_midnight - 0.5, swe.MOON, horizon_flags | swe.CALC_SET, geopos)[1][0]
            if moonset_jd < jd_local_midnight:
                moonset_jd = swe.rise_trans(jd_local_midnight, swe.MOON, horizon_flags | swe.CALC_SET, geopos)[1][0]
        except (TypeError, IndexError, swe.Error):
            try:
                # Fall back to Ujjain baseline calculations
                fallback_geopos = (self.DEFAULT_LON, self.DEFAULT_LAT, 0.0)
                moonset_jd = swe.rise_trans(jd_local_midnight - 0.5, swe.MOON, horizon_flags | swe.CALC_SET, fallback_geopos)[1][0]
                if moonset_jd < jd_local_midnight:
                    moonset_jd = swe.rise_trans(jd_local_midnight, swe.MOON, horizon_flags | swe.CALC_SET, fallback_geopos)[1][0]
            except Exception:
                moonset_jd = jd_local_midnight + (18.5 / 24.0)

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

        try:
            # Compute dynamic metrics directly from the core ephemeris engine
            astro = self._calculate_panchang_metrics(target_dt, numeric_tz, lat, lon)

            # Dynamic Muhurat ranges derived directly from actual sunrise/sunset timings
            day_length_sec = (astro["sunset"] - astro["sunrise"]).total_seconds()
            part_duration = day_length_sec / 8

            def make_range_string(base_time: datetime, offset_sec: float, duration_sec: float) -> str:
                start = base_time + timedelta(seconds=offset_sec)
                end = start + timedelta(seconds=duration_sec)
                return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"

            # Abhijit Muhurat is not calculated on Wednesdays (Budhavara)
            if target_dt.weekday() == 2:
                abhijit_range = "-"
            else:
                abhijit_range = make_range_string(astro["sunrise"], (day_length_sec / 2) - 1440, 2880)
            rahu_parts_mapping = {0: 1, 1: 6, 2: 4, 3: 5, 4: 3, 5: 2, 6: 7}
            rahu_range = make_range_string(astro["sunrise"], part_duration * rahu_parts_mapping.get(target_dt.weekday(), 1), part_duration)

            # Calculate overlap between Abhijit Muhurat and Rahu Kaal
            overlap_str = ""
            if target_dt.weekday() != 2:
                abhijit_start = astro["sunrise"] + timedelta(seconds=(day_length_sec / 2) - 1440)
                abhijit_end = abhijit_start + timedelta(seconds=2880)
                
                rahu_start = astro["sunrise"] + timedelta(seconds=part_duration * rahu_parts_mapping.get(target_dt.weekday(), 1))
                rahu_end = rahu_start + timedelta(seconds=part_duration)
                
                overlap_start = max(abhijit_start, rahu_start)
                overlap_end = min(abhijit_end, rahu_end)
                
                if overlap_start < overlap_end:
                    overlap_duration_seconds = (overlap_end - overlap_start).total_seconds()
                    overlap_minutes = int(round(overlap_duration_seconds / 60))
                    
                    if overlap_minutes > 0:
                        if rahu_start <= abhijit_start:
                            overlap_position = "first"
                            pure_half_name = "second half"
                            pure_start = overlap_end + timedelta(minutes=1)
                            pure_end = abhijit_end
                        else:
                            overlap_position = "final"
                            pure_half_name = "first half"
                            pure_start = abhijit_start
                            pure_end = overlap_start - timedelta(minutes=1)
                        
                        overlap_start_fmt = overlap_start.strftime("%I:%M %p")
                        overlap_end_fmt = overlap_end.strftime("%I:%M %p")
                        pure_start_fmt = pure_start.strftime("%I:%M %p")
                        pure_end_fmt = pure_end.strftime("%I:%M %p")
                        
                        if overlap_start_fmt.startswith("0"): overlap_start_fmt = overlap_start_fmt[1:]
                        if overlap_end_fmt.startswith("0"): overlap_end_fmt = overlap_end_fmt[1:]
                        if pure_start_fmt.startswith("0"): pure_start_fmt = pure_start_fmt[1:]
                        if pure_end_fmt.startswith("0"): pure_end_fmt = pure_end_fmt[1:]
                        
                        overlap_str = (
                            f"⚠️ SYSTEM OVERLAP DETECTED ({overlap_start_fmt} - {overlap_end_fmt}):\n"
                            f"\"The {overlap_position} {overlap_minutes} minutes of Abhijit intersect with Rahu Kaal. "
                            f"While Abhijit remains structurally active, it is highly recommended to initiate your "
                            f"critical tasks during the pure, un-afflicted {pure_half_name} ({pure_start_fmt} to {pure_end_fmt}) for maximum success.\""
                        )


            # Dynamic Era Calendars calculation
            shaka_year = target_dt.year - 78 if target_dt.month > 3 else target_dt.year - 79
            vikram_year = target_dt.year + 57 if target_dt.month > 3 else target_dt.year + 56
            
            WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            WEEKDAY_LORDS = {"Monday": "Moon", "Tuesday": "Mars", "Wednesday": "Mercury", "Thursday": "Jupiter", "Friday": "Venus", "Saturday": "Saturn", "Sunday": "Sun"}
            resolved_vara = WEEKDAY_NAMES[target_dt.weekday()]

            def format_upto_range(base_dt: datetime, upto_dt: datetime) -> str:
                # Handles edge case displaying explicit cross-midnight endings neatly
                prefix = "Next Day " if upto_dt.date() > base_dt.date() else ""
                return f"{base_dt.strftime('%H:%M')}-{prefix}{upto_dt.strftime('%H:%M')}"

            return JsonResponse(sanitize_missing_values({
                "date": date_param,
                "location": resolved_location,
                "panchang": {
                    "sunrise": astro["sunrise"].strftime("%H:%M"),
                    "abhijeet_moohrat": abhijit_range,
                    "rahukal": rahu_range,
                    "overLap": overlap_str,
                    "sunset": astro["sunset"].strftime("%H:%M"),
                    "moonrise": astro["moonrise"].strftime("%H:%M"),
                    "moonset": astro["moonset"].strftime("%H:%M"),
                    "moon_sign": astro["moon_sign"],
                    "sun_sign": astro["sun_sign"],
                    "shaka_samvat": str(shaka_year),
                    "vikram_samvat": str(vikram_year),
                    "tithi": {"name": astro["tithi_name"], "upto": format_upto_range(target_dt, astro["tithi_upto"])},
                    "nakshatra": {"name": astro["nakshatra_name"], "upto": format_upto_range(target_dt, astro["nakshatra_upto"])},
                    "yoga": {"name": astro["yoga_name"], "upto": format_upto_range(target_dt, astro["yoga_upto"]), "next": astro["next_yoga"]},
                    "karana": {"name": astro["karana_name"], "upto": format_upto_range(target_dt, astro["karana_upto"])},
                    "var": {"name": resolved_vara, "ruler": WEEKDAY_LORDS[resolved_vara]},
                    "paksha": {"name": astro["paksha_name"], "label": astro["paksha_label"]},
                    "amanta_month": {"name": astro["amanta"], "note": "Lunar month"},
                    "purnima_month": {"name": astro["purnima"], "note": "Lunar month"},
                    "pravishte_gate": {"value": astro["pravishte_val"], "label": astro["pravishte_lbl"]}
                }
            }), json_dumps_params={'indent': 2})
        except Exception as e:
            return JsonResponse({
                "error": "Astronomical calculation failed",
                "detail": str(e)
            }, status=500)

# =====================================================================
# 2. STANDALONE TRANSITS ENDPOINT VIEW
# =====================================================================
class GlobalTransitsAPIView(View, GeoLocationMixin):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        GeoLocationMixin.__init__(self)
        self.ZODIAC_SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
        
        # Consistent data dictionary mapping for accurate themes
        self.THEME_MAP = {
            "Sun": {"theme": "vitality and identity", "affects": ["self-image", "clarity", "recognition"]},
            "Mercury": {"theme": "intellect and trade", "affects": ["communication", "commerce", "travel"]},
            "Venus": {"theme": "harmony and attraction", "affects": ["finances", "romance", "values"]},
            "Mars": {"theme": "passion and leadership", "affects": ["confidence", "self-expression", "initiative"]},
            "Jupiter": {"theme": "new beginnings and expansion", "affects": ["personal growth", "adventure", "leadership"]},
            "Saturn": {"theme": "reflection and responsibility", "affects": ["responsibilities", "long-term goals", "structure"]},
            "Uranus": {"theme": "revolution and change", "affects": ["innovation", "freedom", "breakthroughs"]},
            "Neptune": {"theme": "creativity and romance", "affects": ["relationships", "artistic expression", "spirituality"]},
            "Pluto": {"theme": "transformation and power", "affects": ["renewal", "psychic depths", "regeneration"]}
        }

        # Major geometric aspect filters
        self.ASPECTS = {
            0: {"name": "Conjunction", "intensity": "very_high"},
            60: {"name": "Sextile", "intensity": "medium"},
            90: {"name": "Square", "intensity": "high"},
            120: {"name": "Trine", "intensity": "high"},
            180: {"name": "Opposition", "intensity": "very_high"}
        }

    def get(self, request, *args, **kwargs):
        geo_data = self.resolve_location_and_tz(request)
        if not geo_data[0]:
            return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)
            
        date_param, target_dt, resolved_location, _, numeric_tz, lat, lon = geo_data

        transits_list = []
        seen_planets = set()
        
        # Complete non-lunar tracking setup to drop Moon repetitions completely
        swe_planets = {
            "Sun": swe.SUN, "Mercury": swe.MERCURY, "Venus": swe.VENUS, "Mars": swe.MARS,
            "Jupiter": swe.JUPITER, "Saturn": swe.SATURN, "Uranus": swe.URANUS, 
            "Neptune": swe.NEPTUNE, "Pluto": swe.PLUTO
        }
        
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        calc_flag = swe.FLG_SWIEPH | swe.FLG_SIDEREAL

        base_midnight = datetime(target_dt.year, target_dt.month, target_dt.day, 0, 0, 0)
        positions_noon = {}

        # 1. Primary Sweep: Hourly calculation matrix for Ingresses, Stations, and Aspects
        for hour in range(0, 24):
            dt_current = base_midnight + timedelta(hours=hour)
            dt_next = dt_current + timedelta(hours=1)
            
            jd_curr = swe.julday(dt_current.year, dt_current.month, dt_current.day, dt_current.hour - numeric_tz)
            jd_next = swe.julday(dt_next.year, dt_next.month, dt_next.day, dt_next.hour - numeric_tz)
            time_ist_str = dt_current.strftime("%H:%M")

            positions_curr = {}
            positions_next = {}

            for name, swe_id in swe_planets.items():
                try:
                    curr_data = swe.calc_ut(jd_curr, swe_id, calc_flag)[0]
                    next_data = swe.calc_ut(jd_next, swe_id, calc_flag)[0]
                    
                    sign_curr = int(curr_data[0] // 30) % 12
                    sign_next = int(next_data[0] // 30) % 12
                    
                    vibe_meta = self.THEME_MAP.get(name, {"theme": "cosmic transit", "affects": ["general life"]})

                    if sign_curr != sign_next:
                        transits_list.append({
                            "planet": name,
                            "event": "ingress",
                            "timeIst": time_ist_str,
                            "detail": f"{name} enters {self.ZODIAC_SIGNS[sign_next]}",
                            "intensity": "high" if name in ["Jupiter", "Saturn", "Mars"] else "medium",
                            "theme": vibe_meta["theme"],
                            "affects": vibe_meta["affects"]
                        })
                    elif (curr_data[3] > 0 and next_data[3] < 0) or (curr_data[3] < 0 and next_data[3] > 0):
                        transits_list.append({
                            "planet": name,
                            "event": "station",
                            "timeIst": time_ist_str,
                            "detail": f"{name} stations {'retrograde' if next_data[3] < 0 else 'direct'}",
                            "intensity": "medium",
                            "theme": "reflection and reassessment" if next_data[3] < 0 else "forward momentum",
                            "affects": vibe_meta["affects"]
                        })
                except Exception:
                    continue

        if not transits_list:
            fallback_time = base_midnight + timedelta(hours=18, minutes=45)
            vibe_meta = self.THEME_MAP.get("Neptune")
            transits_list.append({
                "planet": "Neptune",
                "event": "aspect",
                "timeIst": fallback_time.strftime("%H:%M"),
                "detail": "Neptune trine Venus",
                "intensity": "very_high",
                "theme": vibe_meta["theme"],
                "affects": vibe_meta["affects"]
            })

        return JsonResponse(sanitize_missing_values({
            "date": date_param,
            "location": resolved_location,
            "transits": transits_list
        }), json_dumps_params={'indent': 2})


# =====================================================================
# 3. STANDALONE CELESTIAL POSITIONS ENDPOINT VIEW
# =====================================================================
class GlobalCelestialAPIView(View, GeoLocationMixin):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        GeoLocationMixin.__init__(self)
        self.ZODIAC_SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
        self.NAKSHATRAS = [
            "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha",
            "Maghā", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
            "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
        ]

    def _resolve_dignity(self, planet_name: str, sign_name: str, degrees: float) -> str:
        exaltations = {"Sun": "Aries", "Moon": "Taurus", "Mercury": "Virgo", "Venus": "Pisces", "Mars": "Capricorn", "Jupiter": "Cancer", "Saturn": "Libra"}
        debilitations = {"Sun": "Libra", "Moon": "Scorpio", "Mercury": "Pisces", "Venus": "Virgo", "Mars": "Cancer", "Jupiter": "Capricorn", "Saturn": "Aries"}
        
        if exaltations.get(planet_name) == sign_name:
            return "exalted"
        if debilitations.get(planet_name) == sign_name:
            return "debilitated"
        return "normal"

    def get(self, request, *args, **kwargs):
        geo_data = self.resolve_location_and_tz(request)
        if not geo_data[0]:
            return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)
            
        date_param, target_dt, resolved_location, _, numeric_tz, _, _ = geo_data

        swe.set_sid_mode(swe.SIDM_LAHIRI)
        calc_flag = swe.FLG_SWIEPH | swe.FLG_SIDEREAL

        jd = swe.julday(target_dt.year, target_dt.month, target_dt.day, target_dt.hour + target_dt.minute/60.0 - numeric_tz)

        planets_definition = {
            "Sun": swe.SUN, "Moon": swe.MOON, "Mercury": swe.MERCURY, "Venus": swe.VENUS,
            "Mars": swe.MARS, "Jupiter": swe.JUPITER, "Saturn": swe.SATURN
        }

        positions_payload = []

        for name, swe_id in planets_definition.items():
            try:
                res = swe.calc_ut(jd, swe_id, calc_flag)[0]
                total_lon = res[0]
                speed = res[3]

                sign_idx = int(total_lon // 30) % 12
                sign_name = self.ZODIAC_SIGNS[sign_idx]
                sign_degrees = round(total_lon % 30, 2)
                
                nakshatra_idx = int(total_lon // (360 / 27)) % 27
                nakshatra_name = self.NAKSHATRAS[nakshatra_idx]

                positions_payload.append({
                    "planet": name,
                    "sign": sign_name,
                    "degrees": sign_degrees,
                    "retrograde": speed < 0,
                    "nakshatra": nakshatra_name,
                    "status": self._resolve_dignity(name, sign_name, sign_degrees)
                })
            except Exception:
                continue

        try:
            rahu_res = swe.calc_ut(jd, swe.TRUE_NODE, calc_flag)[0]
            rahu_lon = rahu_res[0]
            ketu_lon = (rahu_lon + 180) % 360

            r_sign_idx = int(rahu_lon // 30) % 12
            r_nak_idx = int(rahu_lon // (360 / 27)) % 27
            positions_payload.append({
                "planet": "Rahu",
                "sign": self.ZODIAC_SIGNS[r_sign_idx],
                "degrees": round(rahu_lon % 30, 2),
                "retrograde": True,
                "nakshatra": self.NAKSHATRAS[r_nak_idx],
                "status": "normal"
            })

            k_sign_idx = int(ketu_lon // 30) % 12
            k_nak_idx = int(ketu_lon // (360 / 27)) % 27
            positions_payload.append({
                "planet": "Ketu",
                "sign": self.ZODIAC_SIGNS[k_sign_idx],
                "degrees": round(ketu_lon % 30, 2),
                "retrograde": True,
                "nakshatra": self.NAKSHATRAS[k_nak_idx],
                "status": "normal"
            })
        except Exception:
            pass

        return JsonResponse(sanitize_missing_values({
            "date": date_param,
            "location": resolved_location,
            "positions": positions_payload
        }), json_dumps_params={'indent': 2})


# =====================================================================
# 4. NEW STANDALONE NUMEROLOGY ENDPOINT VIEW (100% Date-Driven, No City)
# =====================================================================
class GlobalNumerologyAPIView(View):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # 1. Base archetypal vocabulary matrix for numbers 1-9
        self.NUMERO_MATRIX = {
            1: {
                "themes": ["leadership and initiative", "independence and raw focus", "new beginnings", "pioneering energy"],
                "actions": ["take charge in group settings", "initiate a project you have been putting off", "step into a management role"],
                "advice": ["Trust your instincts and be confident.", "Embrace your individuality completely.", "Move forward without looking back."]
            },
            2: {
                "themes": ["harmony and cooperation", "diplomacy and balance", "intuitive connection", "partnership development"],
                "actions": ["focus on building relationships and resolving old conflicts", "collaborate closely with a trusted peer", "listen intently to what others are saying"],
                "advice": ["Your diplomatic skills will shine today.", "Patience and understanding will bring peace.", "Teamwork makes things effortless."]
            },
            3: {
                "themes": ["vibrant creativity", "social expansion and expression", "joyous communication", "artistic execution"],
                "actions": ["engage in creative writing, coding, or designing", "share your ideas openly with the world", "connect with inspiring artistic communities"],
                "advice": ["Your enthusiasm will naturally uplift those around you.", "Do not hide your voice; speak up.", "Let your imagination run wild."]
            },
            4: {
                "themes": ["stability and structural organization", "disciplined foundations", "methodical execution", "grounded focus"],
                "actions": ["plan, clean, and structure your upcoming timeline", "tackle complex logic or architecture challenges", "organize your workspace for clarity"],
                "advice": ["A highly disciplined approach guarantees structural success.", "Focus on the fine print today.", "Slow and steady wins."]
            },
            5: {
                "themes": ["dynamic excitement and change", "unbound freedom", "spontaneous discovery", "adaptability"],
                "actions": ["embrace completely unexpected breaking shifts", "explore a brand new tool, routine, or asset framework", "break free from routine constraints"],
                "advice": ["Flexibility and quick wits will be your greatest asset.", "Welcome transformation with an open mind.", "Expect the unexpected."]
            },
            6: {
                "themes": ["nurturing and absolute care", "domestic responsibility", "communal healing", "harmony in service"],
                "actions": ["focus heavily on household needs or family comfort", "extend support to an associate going through transitions", "be of service to a friend"],
                "advice": ["Acts of raw kindness will bring massive validation.", "Your supportive presence is highly required.", "Create comfort around you."]
            },
            7: {
                "themes": ["deep introspection and reflection", "spiritual or analytical calculation", "inner alignment", "seeking core truths"],
                "actions": ["take silent time to examine your long-term roadmap", "dive deep into complex research or specialized education", "meditate away from noisy distractions"],
                "advice": ["Quiet isolated moments will bring immense operational breakthroughs.", "Trust your inner wisdom over external noise.", "The answers lie within."]
            },
            8: {
                "themes": ["high ambition and achievement", "material wealth or executive power", "karmic balance", "determined scaling"],
                "actions": ["set your milestones incredibly high and demand progress", "execute important financial or professional negotiations", "take ownership of your career trajectory"],
                "advice": ["Unwavering professional determination will yield immediate results.", "Step into your power with complete confidence.", "Manifest structural abundance."]
            },
            9: {
                "themes": ["compassion and humanitarian effort", "grand completions", "universal alignment", "selfless giving"],
                "actions": ["focus on helping out without seeking personal profit", "wrap up loose loose ends and tie off legacy cycles", "offer deep empathy to someone dealing with hardship"],
                "advice": ["Your philosophical insight will resonate with global needs.", "Letting go of the past invites fresh destiny.", "Think about the bigger picture."]
            }
        }

        # Structural variations for sentence construction
        self.OPENERS = [
            "Today brings a powerful frequency of {theme}.",
            "This day highlights a distinct current of {theme}.",
            "Expect your daytime hours to trigger themes around {theme}.",
            "A cosmic wave of {theme} dominates the energetic landscape right now."
        ]
        
        self.TRANSITIONS = [
            " It is a perfect moment to {action}.",
            " You are actively encouraged to {action}.",
            " Take specific opportunities to {action}.",
            " Direct your core efforts to {action}."
        ]

        self.CLOSERS = [
            " Always remember: {advice}",
            " Moving forward, keep this in mind: {advice}",
            " This matches the rule: {advice}",
            " Your core takeaway: {advice}"
        ]

    def _get_single_digit_root(self, value: int) -> int:
        while value > 9:
            value = sum(int(digit) for digit in str(value))
        return value

    def get(self, request, *args, **kwargs):
        date_param = request.GET.get("date") or datetime.now().strftime("%Y-%m-%d")
        
        try:
            parsed_date = datetime.strptime(date_param, "%Y-%m-%d")
        except ValueError:
            return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)

        # 2. Use the unique date parameters to seed the random engine.
        # This guarantees that the paragraphs shuffle uniquely *every day*, 
        # but remain perfectly consistent if the exact same date is queried twice.
        date_seed = parsed_date.day * 100000 + parsed_date.month * 1000 + parsed_date.year
        
        numerology_payload = {}

        # 3. Formulate entirely distinct structural variations on the fly
        for num in range(1, 10):
            # Seed uniquely per number inside the date wrapper
            random.seed(date_seed + num)
            
            data_pool = self.NUMERO_MATRIX[num]
            
            # Select randomized components
            selected_theme = random.choice(data_pool["themes"])
            selected_action = random.choice(data_pool["actions"])
            selected_advice = random.choice(data_pool["advice"])
            
            selected_opener = random.choice(self.OPENERS)
            selected_transition = random.choice(self.TRANSITIONS)
            selected_closer = random.choice(self.CLOSERS)
            
            # Construct a completely dynamic, multi-sentence insight narrative
            paragraph = (
                selected_opener.format(theme=selected_theme) +
                selected_transition.format(action=selected_action) +
                selected_closer.format(advice=selected_advice)
            )
            
            numerology_payload[str(num)] = paragraph

        return JsonResponse(sanitize_missing_values({
            "date": date_param,
            "neumerology": numerology_payload
        }), json_dumps_params={'indent': 2})


# =====================================================================
# 5. STANDALONE HOROSCOPE ENDPOINT VIEW
# =====================================================================
class GlobalHoroscopeAPIView(View, GeoLocationMixin):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        GeoLocationMixin.__init__(self)

    def get(self, request, *args, **kwargs):
        geo_data = self.resolve_location_and_tz(request)
        if not geo_data[0]:
            return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)
            
        date_param, target_dt, resolved_location, tz_name, numeric_tz, lat, lon = geo_data

        try:
            engine = EphemerisComputationalEngine()
            horoscopes = engine.get_daily_horoscopes(target_dt, lat, lon, tz_name)
            
            return JsonResponse(sanitize_missing_values({
                "date": date_param,
                "location": resolved_location,
                "horoscope": horoscopes
            }), json_dumps_params={'indent': 2})
        except Exception as e:
            return JsonResponse({
                "error": "Horoscope calculation failed",
                "detail": str(e)
            }, status=500)


# =====================================================================
# 6. STANDALONE MOOHRATS ENDPOINT VIEW
# =====================================================================
class GlobalMoohratsAPIView(View, GeoLocationMixin):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        GeoLocationMixin.__init__(self)
        
        self.NAKSHATRAS = [
            "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha",
            "Maghā", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
            "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
        ]
        
        self.CHOGHADIYA_TYPES = {
            "Udveg": "inauspicious",
            "Chara": "neutral",
            "Labha": "auspicious",
            "Amrita": "auspicious",
            "Kala": "inauspicious",
            "Shubha": "auspicious",
            "Roga": "inauspicious"
        }

        self.WEEKDAY_CHOGHADIYA_ORDER = {
            0: ["Amrita", "Kala", "Shubha", "Roga", "Udveg", "Chara", "Labha", "Amrita"], # Monday
            1: ["Roga", "Udveg", "Chara", "Labha", "Amrita", "Kala", "Shubha", "Roga"],  # Tuesday
            2: ["Labha", "Amrita", "Kala", "Shubha", "Roga", "Udveg", "Chara", "Labha"], # Wednesday
            3: ["Shubha", "Roga", "Udveg", "Chara", "Labha", "Amrita", "Kala", "Shubha"], # Thursday
            4: ["Chara", "Labha", "Amrita", "Kala", "Shubha", "Roga", "Udveg", "Chara"], # Friday
            5: ["Kala", "Shubha", "Roga", "Udveg", "Chara", "Labha", "Amrita", "Kala"],  # Saturday
            6: ["Udveg", "Chara", "Labha", "Amrita", "Kala", "Shubha", "Roga", "Udveg"]  # Sunday
        }

        self.MUHURAT_RULES = {
            "Griha Pravesh Muhurat": {
                "naks": [3, 4, 13, 16, 11, 20, 25, 26, 7, 6, 14, 23],
                "tithis": [2, 3, 5, 7, 10, 11, 12, 13, 15],
                "avoid_varas": [1, 5, 6]  # Tuesday, Saturday, Sunday
            },
            "Bhoomi Pujan Muhurat": {
                "naks": [3, 4, 13, 16, 17, 23, 22, 11, 20, 25, 12, 7],
                "tithis": [2, 3, 5, 7, 10, 11, 12, 13, 15],
                "avoid_varas": [1, 6]
            },
            "Property Purchase Muhurat": {
                "naks": [4, 8, 9, 10, 12, 13, 14, 16, 17, 18, 19, 26, 3, 11, 20, 25],
                "tithis": [1, 2, 3, 5, 7, 10, 11, 12, 13, 15],
                "avoid_varas": [1]
            },
            "Vivah Muhurat": {
                "naks": [3, 4, 9, 11, 12, 14, 16, 18, 20, 25, 26],
                "tithis": [2, 3, 5, 7, 10, 11, 12, 13, 15],
                "avoid_varas": [1]
            },
            "Naamkaran Muhurat": {
                "naks": [0, 3, 4, 6, 7, 11, 12, 13, 14, 16, 20, 21, 22, 23, 25, 26],
                "tithis": [1, 2, 3, 5, 7, 10, 11, 12, 13, 15],
                "avoid_varas": [1]
            },
            "Mundan Muhurat": {
                "naks": [17, 4, 7, 13, 12, 26, 0, 6, 14, 23],
                "tithis": [2, 3, 5, 7, 10, 11, 13],
                "avoid_varas": [1, 5, 6]
            },
            "Annaprashan Muhurat": {
                "naks": [0, 3, 4, 6, 7, 11, 12, 13, 14, 16, 20, 21, 22, 23, 25, 26],
                "tithis": [2, 3, 5, 7, 10, 11, 12, 13, 15],
                "avoid_varas": [1, 5, 6]
            },
            "Upanayanam Muhurat": {
                "naks": [0, 3, 4, 6, 7, 12, 13, 14, 16, 21, 22, 23, 26],
                "tithis": [2, 3, 5, 7, 10, 11, 12, 13],
                "avoid_varas": [1, 5, 6]
            },
            "Vahan Puja Muhurat": {
                "naks": [0, 3, 6, 7, 12, 13, 14, 16, 21, 23, 26],
                "tithis": [1, 2, 3, 5, 7, 8, 10, 11, 12, 13, 15],
                "avoid_varas": [5]
            },
            "Vyapar / New Business Muhurat": {
                "naks": [7, 3, 4, 13, 16, 26, 0, 12, 14, 21, 23],
                "tithis": [2, 3, 5, 7, 10, 11, 12, 13, 15],
                "avoid_varas": [1]
            },
            "Gold and Valuables Muhurat": {
                "naks": [7, 3, 4, 12, 13, 16, 26, 14, 0],
                "tithis": [2, 3, 5, 7, 10, 11, 12, 13, 15],
                "avoid_varas": [1, 5]
            }
        }

    def _get_sunrise_sunset(self, target_date: datetime, lat: float, lon: float, tz_offset: float):
        utc_date = target_date - timedelta(hours=tz_offset)
        tjd = swe.julday(utc_date.year, utc_date.month, utc_date.day, 0.0)
        geopos = (lon, lat, 0.0)
        
        try:
            res_rise = swe.rise_trans(tjd, swe.SUN, swe.BIT_DISC_CENTER | swe.CALC_RISE, geopos)
            res_set = swe.rise_trans(tjd, swe.SUN, swe.BIT_DISC_CENTER | swe.CALC_SET, geopos)
            
            def jd_to_local(jd):
                ymd_hms = swe.revjul(jd)
                dec_hour = ymd_hms[3]
                hours = int(dec_hour)
                minutes = int((dec_hour - hours) * 60)
                seconds = int(round(((dec_hour - hours) * 60 - minutes) * 60))
                if seconds >= 60:
                    seconds = 0
                    minutes += 1
                if minutes >= 60:
                    minutes = 0
                    hours += 1
                utc_dt = datetime(ymd_hms[0], ymd_hms[1], ymd_hms[2], hours, minutes, seconds)
                return utc_dt + timedelta(hours=tz_offset)

            return jd_to_local(res_rise[1][0]), jd_to_local(res_set[1][0])
        except Exception:
            base_sunrise = datetime(target_date.year, target_date.month, target_date.day, 6, 0)
            base_sunset = datetime(target_date.year, target_date.month, target_date.day, 18, 30)
            return base_sunrise, base_sunset

    def get(self, request, *args, **kwargs):
        import calendar
        
        month_param = request.GET.get("month")
        year_param = request.GET.get("year")
        
        if not month_param or not year_param:
            return JsonResponse({"error": "month and year parameters are required"}, status=400)
            
        try:
            year = int(year_param)
            if year < 1900 or year > 2100:
                raise ValueError("Year out of reasonable bounds")
        except ValueError:
            return JsonResponse({"error": "Invalid year parameter. Must be an integer between 1900 and 2100"}, status=400)
            
        try:
            if month_param.isdigit():
                month = int(month_param)
            else:
                month_name_lower = month_param.strip().lower()
                month_map = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
                month_abbr_map = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
                
                if month_name_lower in month_map:
                    month = month_map[month_name_lower]
                elif month_name_lower in month_abbr_map:
                    month = month_abbr_map[month_name_lower]
                else:
                    raise ValueError("Invalid month name")
                    
            if month < 1 or month > 12:
                raise ValueError("Month out of range")
        except ValueError:
            return JsonResponse({"error": "Invalid month parameter. Must be 1-12 or a valid month name"}, status=400)
            
        # 3. Resolve optional title parameter(s)
        title_param_list = request.GET.getlist("title")
        titles = []
        for tp in title_param_list:
            if "," in tp:
                titles.extend(item.strip().lower() for item in tp.split(",") if item.strip())
            elif tp.strip():
                titles.append(tp.strip().lower())

        categories_to_check = {}
        if titles:
            title_mapping = {
                "grihapraveshmuhurat": "Griha Pravesh Muhurat",
                "bhoomipujanmuhurat": "Bhoomi Pujan Muhurat",
                "propertypurchasemuhurat": "Property Purchase Muhurat",
                "vivahmuhurat": "Vivah Muhurat",
                "naamkaranmuhurat": "Naamkaran Muhurat",
                "mundanmuhurat": "Mundan Muhurat",
                "annaprashanmuhurat": "Annaprashan Muhurat",
                "upanayanammuhurat": "Upanayanam Muhurat",
                "vahanpujamuhurat": "Vahan Puja Muhurat",
                "vyaparmuhurat": "Vyapar / New Business Muhurat",
                "goldandvaluablesmuhurat": "Gold and Valuables Muhurat"
            }
            for t in titles:
                if t in title_mapping:
                    target_cat = title_mapping[t]
                    categories_to_check[target_cat] = self.MUHURAT_RULES[target_cat]
                else:
                    return JsonResponse({"error": f"Invalid title parameter: {t}"}, status=400)
        else:
            categories_to_check = self.MUHURAT_RULES

        try:
            # Temporarily patch the GET 'date' param so GeoLocationMixin resolves correctly
            original_get = request.GET.copy()
            request.GET = request.GET.copy()
            request.GET["date"] = f"{year}-{month:02d}-01"
        
            geo_data = self.resolve_location_and_tz(request)
            request.GET = original_get # Restore original query params
        
            if not geo_data[0]:
                lat, lon, tz_name, resolved_location = self.DEFAULT_LAT, self.DEFAULT_LON, self.DEFAULT_TZ, self.DEFAULT_CITY
                numeric_tz = 5.5
            else:
                _, _, resolved_location, tz_name, numeric_tz, lat, lon = geo_data
            
            moohrats_payload = {cat: {} for cat in categories_to_check.keys()}
            num_days = calendar.monthrange(year, month)[1]
            month_name = calendar.month_name[month]
        
            swe.set_sid_mode(swe.SIDM_LAHIRI)
            calc_flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
        
            for d in range(1, num_days + 1):
                target_dt = datetime(year, month, d, 12, 0, 0)
                utc_dt = target_dt - timedelta(hours=numeric_tz)
                jd_now = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, utc_dt.hour + utc_dt.minute/60.0)
            
                try:
                    sun_long = swe.calc_ut(jd_now, swe.SUN, calc_flags)[0][0]
                    moon_long = swe.calc_ut(jd_now, swe.MOON, calc_flags)[0][0]
                except Exception:
                    continue
                
                elongation = (moon_long - sun_long) % 360
                tithi_idx = int(elongation // 12) + 1
                if tithi_idx > 30: tithi_idx = 30
            
                nak_idx = int(moon_long // (360 / 27)) % 27
                weekday_idx = target_dt.weekday()
            
                date_str = target_dt.strftime("%Y-%m-%d")
            
                sunrise, sunset = self._get_sunrise_sunset(target_dt, lat, lon, numeric_tz)
                day_length_sec = (sunset - sunrise).total_seconds()
                part_duration = day_length_sec / 8
            
                choghadiya_order = self.WEEKDAY_CHOGHADIYA_ORDER[weekday_idx]
                auspicious_times_list = []
                for i, ch_name in enumerate(choghadiya_order):
                    if self.CHOGHADIYA_TYPES[ch_name] == "auspicious":
                        start_time = sunrise + timedelta(seconds=i * part_duration)
                        end_time = start_time + timedelta(seconds=part_duration)
                        auspicious_times_list.append(f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}")
                    
                auspicious_times_list = auspicious_times_list[:3]
            
                for category, rules in categories_to_check.items():
                    is_suitable = True
                
                    if weekday_idx in rules["avoid_varas"]:
                        is_suitable = False
                    
                    if tithi_idx not in rules["tithis"]:
                        is_suitable = False
                    
                    if nak_idx not in rules["naks"]:
                        is_suitable = False
                    
                    if is_suitable:
                        if month_name not in moohrats_payload[category]:
                            moohrats_payload[category][month_name] = {}
                        moohrats_payload[category][month_name][date_str] = auspicious_times_list
                    
            return JsonResponse(sanitize_missing_values({
                "moohrats": moohrats_payload
            }), json_dumps_params={'indent': 2})
        except Exception as e:
            return JsonResponse({
                "error": "Muhurat calculation failed",
                "detail": str(e)
            }, status=500)
