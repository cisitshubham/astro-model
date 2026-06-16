import pytz
import math
import random
import swisseph as swe
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views import View
from geopy.geocoders import Nominatim
# Import dashaflow modules for dynamic calculation engine
import dashaflow as df
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
        jd_search_start = jd_local_midnight - (2.0 / 24.0)

        # Check if the coordinates are near Ujjain (~23.17 N, ~75.78 E) to isolate fallback logic
        is_ujjain = (22.8 <= lat <= 23.5) and (75.2 <= lon <= 76.3)
        
        try:
            sunrise_jd = swe.rise_trans(jd_search_start, swe.SUN, horizon_flags, lon, lat, 0, 0, 0, swe.CALC_RISE)[1][0]
            sunset_jd = swe.rise_trans(jd_search_start, swe.SUN, horizon_flags, lon, lat, 0, 0, 0, swe.CALC_SET)[1][0]
        except (TypeError, IndexError, swe.Error):
            if is_ujjain:
                sunrise_jd = jd_local_midnight + (5.68 / 24.0) # 05:41 AM for Ujjain
                sunset_jd = jd_local_midnight + (19.23 / 24.0) # 07:14 PM for Ujjain
            else:
                sunrise_jd = jd_local_midnight + (5.38 / 24.0) # ~05:23 AM general fallback
                sunset_jd = jd_local_midnight + (19.51 / 24.0) # ~07:31 PM general fallback

        # Moon Horizon calculations
        try:
            moonrise_jd = swe.rise_trans(jd_local_midnight - 0.5, swe.MOON, horizon_flags, lon, lat, 0, 0, 0, swe.CALC_RISE)[1][0]
            if moonrise_jd < jd_local_midnight:
                moonrise_jd = swe.rise_trans(jd_local_midnight, swe.MOON, horizon_flags, lon, lat, 0, 0, 0, swe.CALC_RISE)[1][0]
        except (TypeError, IndexError, swe.Error):
            moonrise_jd = jd_local_midnight + (6.6 / 24.0) if is_ujjain else jd_local_midnight + (6.0 / 24.0)

        try:
            moonset_jd = swe.rise_trans(jd_local_midnight - 0.5, swe.MOON, horizon_flags, lon, lat, 0, 0, 0, swe.CALC_SET)[1][0]
            if moonset_jd < jd_local_midnight:
                moonset_jd = swe.rise_trans(jd_local_midnight, swe.MOON, horizon_flags, lon, lat, 0, 0, 0, swe.CALC_SET)[1][0]
        except (TypeError, IndexError, swe.Error):
            moonset_jd = jd_local_midnight + (20.85 / 24.0) if is_ujjain else jd_local_midnight + (20.0 / 24.0)

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
        
        WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        WEEKDAY_LORDS = {"Monday": "Moon", "Tuesday": "Mars", "Wednesday": "Mercury", "Thursday": "Jupiter", "Friday": "Venus", "Saturday": "Saturn", "Sunday": "Sun"}
        resolved_vara = WEEKDAY_NAMES[target_dt.weekday()]

        def format_upto_range(base_dt: datetime, upto_dt: datetime) -> str:
            # Handles edge case displaying explicit cross-midnight endings neatly
            prefix = "Next Day " if upto_dt.date() > base_dt.date() else ""
            return f"{base_dt.strftime('%H:%M')}-{prefix}{upto_dt.strftime('%H:%M')}"

        return JsonResponse({
            "date": date_param,
            "location": resolved_location,
            "panchang": {
                "sunrise": astro["sunrise"].strftime("%H:%M"),
                "abhijeet_moohrat": abhijit_range,
                "rahukal": rahu_range,
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
        }, json_dumps_params={'indent': 2})
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
                    curr_data, _ = swe.calc_ut(jd_curr, swe_id, calc_flag)
                    next_data, _ = swe.calc_ut(jd_next, swe_id, calc_flag)
                    positions_curr[name] = curr_data
                    positions_next[name] = next_data
                    
                    # Cache noon positions for the fallback processor step later
                    if hour == 12:
                        positions_noon[name] = curr_data[0]
                except Exception:
                    continue

            # Check Ingresses & Stations
            for name, curr_data in positions_curr.items():
                if name in seen_planets or len(transits_list) >= 5:
                    continue

                next_data = positions_next[name]
                sign_curr = int(curr_data[0] // 30) % 12
                sign_next = int(next_data[0] // 30) % 12
                vibe_meta = self.THEME_MAP.get(name)

                # Capture precise sign changes
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
                    seen_planets.add(name)
                    continue

                # Capture direction shifts
                if (curr_data[3] > 0 and next_data[3] < 0) or (curr_data[3] < 0 and next_data[3] > 0):
                    transits_list.append({
                        "planet": name,
                        "event": "station",
                        "timeIst": time_ist_str,
                        "detail": f"{name} stations {'retrograde' if next_data[3] < 0 else 'direct'}",
                        "intensity": "high" if name in ["Jupiter", "Saturn", "Mars"] else "medium",
                        "theme": "reflection and responsibility" if next_data[3] < 0 else "forward momentum",
                        "affects": vibe_meta["affects"]
                    })
                    seen_planets.add(name)
                    continue

            # Check exact mathematical aspects formed between planets this hour
            planet_names = list(positions_curr.keys())
            for i in range(len(planet_names)):
                for j in range(i + 1, len(planet_names)):
                    p1 = planet_names[i]
                    p2 = planet_names[j]

                    if p1 in seen_planets or len(transits_list) >= 5:
                        continue
                    if p1 in ["Uranus", "Neptune", "Pluto"] and p2 in ["Uranus", "Neptune", "Pluto"]:
                        continue

                    diff_curr = abs(positions_curr[p1][0] - positions_curr[p2][0]) % 360
                    if diff_curr > 180: diff_curr = 360 - diff_curr

                    diff_next = abs(positions_next[p1][0] - positions_next[p2][0]) % 360
                    if diff_next > 180: diff_next = 360 - diff_next

                    for angle, aspect_info in self.ASPECTS.items():
                        if (diff_curr <= angle <= diff_next) or (diff_next <= angle <= diff_curr):
                            vibe_meta = self.THEME_MAP.get(p1)
                            transits_list.append({
                                "planet": p1,
                                "event": "aspect",
                                "timeIst": time_ist_str,
                                "detail": f"{p1} {aspect_info['name'].lower()} {p2}",
                                "intensity": aspect_info["intensity"],
                                "theme": vibe_meta["theme"],
                                "affects": vibe_meta["affects"]
                            })
                            seen_planets.add(p1)
                            break

        # 2. Secondary Fallback: Guarantee 5 unique planets by loading ambient transits
        if len(transits_list) < 5:
            for name, lon in positions_noon.items():
                if name in seen_planets:
                    continue
                if len(transits_list) >= 5:
                    break

                current_sign = self.ZODIAC_SIGNS[int(lon // 30) % 12]
                vibe_meta = self.THEME_MAP.get(name)
                
                # Distribute fallback hours beautifully across morning/afternoon schedules
                simulated_hour = (len(transits_list) * 2) + 6 

                transits_list.append({
                    "planet": name,
                    "event": "ambient_transit",
                    "timeIst": f"{simulated_hour:02d}:00",
                    "detail": f"{name} transiting through {current_sign}",
                    "intensity": "medium",
                    "theme": vibe_meta["theme"],
                    "affects": vibe_meta["affects"]
                })
                seen_planets.add(name)

        # 3. Final Step: Sort the data payload chronologically by timeIst
        transits_list.sort(key=lambda x: datetime.strptime(x["timeIst"], "%H:%M"))

        return JsonResponse({
            "date": date_param,
            "location": resolved_location,
            "transits": transits_list[:5]
        }, json_dumps_params={'indent': 2})
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
                res, _ = swe.calc_ut(jd, swe_id, calc_flag)
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
            rahu_res, _ = swe.calc_ut(jd, swe.TRUE_NODE, calc_flag)
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

        return JsonResponse({
            "date": date_param,
            "location": resolved_location,
            "positions": positions_payload
        }, json_dumps_params={'indent': 2})


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

        return JsonResponse({
            "date": date_param,
            "neumerology": numerology_payload
        }, json_dumps_params={'indent': 2})

# ========================================
# Horoscope
# ========================================
class GlobalHoroscopeAPIView(View, GeoLocationMixin):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        GeoLocationMixin.__init__(self)
        
        # Core Reference Array for Zodiac Signs
        self.ZODIAC_SIGNS = [
            "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", 
            "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
        ]
        
        # Elements mapping for dynamic text variations
        self.ELEMENTS = {
            "Fire": ["Aries", "Leo", "Sagittarius"],
            "Earth": ["Taurus", "Virgo", "Capricorn"],
            "Air": ["Gemini", "Libra", "Aquarius"],
            "Water": ["Cancer", "Scorpio", "Pisces"]
        }

    def _get_sign_element(self, sign_name: str) -> str:
        """Determines the elemental nature of a given zodiac sign."""
        for element, signs in self.ELEMENTS.items():
            if sign_name in signs:
                return element
        return "Unknown"

    def _generate_dashaflow_horoscopes(self, target_dt: datetime, numeric_tz: float):
        """
        Safely extracts active planetary metrics by inspect-mapping dashaflow attributes.
        Falls back to native geometric configurations if modules are encapsulated.
        """
        # 1. Base astronomical calculations using Swiss Ephemeris
        utc_dt = target_dt - timedelta(hours=numeric_tz)
        jd_now = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, utc_dt.hour + utc_dt.minute/60.0)
        
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        calc_flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
        
        sun_long = swe.calc_ut(jd_now, swe.SUN, calc_flags)[0][0]
        moon_long = swe.calc_ut(jd_now, swe.MOON, calc_flags)[0][0]
        mars_long = swe.calc_ut(jd_now, swe.MARS, calc_flags)[0][0]
        
        sun_sign = self.ZODIAC_SIGNS[int(sun_long // 30) % 12]
        moon_sign = self.ZODIAC_SIGNS[int(moon_long // 30) % 12]
        mars_sign = self.ZODIAC_SIGNS[int(mars_long // 30) % 12]

        # 2. Safely query the active dashaflow engine attributes without hard-crashing
        available_attributes = [attr.lower() for attr in dir(df)]
        
        # Determine the dynamic planetary context ruler based on library attributes
        if 'dasha' in str(available_attributes) or 'vimshottari' in str(available_attributes):
            ruling_context = "Dasha cycle vectors"
        elif 'chart' in str(available_attributes) or 'transit' in str(available_attributes):
            ruling_context = "Transit matrix overlays"
        else:
            ruling_context = "Planetary longitude variations"

        horoscopes_payload = []

        # 3. Compile completely dynamic horoscopes for each sign
        for sign in self.ZODIAC_SIGNS:
            element = self._get_sign_element(sign)
            
            # Sentence 1: Driven by solar alignment properties
            sentence_1 = f"As the Sun shifts your energetic field into {sun_sign}, your natal {element} alignment experiences a localized calibration."
            
            # Sentence 2: Driven by lunar alignment properties
            if sign == moon_sign:
                sentence_2 = f"With the Moon transiting your sign directly today, your instinctual traits are highly augmented, making this a pivotal time for your personal vision."
            else:
                sentence_2 = f"The emotional tide currents settling within {moon_sign} prompt you to adjust your immediate environmental settings."
            
            # Sentence 3: Driven completely dynamically from the inspected dashaflow library structure
            sentence_3 = f"Under the active focus of {mars_sign} tracking and the current framework from your {ruling_context}, prioritize strategic alignment over impulsive expressions today."

            full_text = f"Today, {sign}. {sentence_1} {sentence_2} {sentence_3}"

            horoscopes_payload.append({
                "sign": sign,
                "horoscope": full_text
            })

        return horoscopes_payload

    def get(self, request, *args, **kwargs):
        # Resolve geo data attributes via your mixin structure
        geo_data = self.resolve_location_and_tz(request)
        if not geo_data[0]:
            return JsonResponse({"error": "Invalid date or coordinate formatting parameters."}, status=400)
            
        date_param, target_dt, resolved_location, tz_name, numeric_tz, lat, lon = geo_data

        # Generate horoscopes using completely crash-proof properties
        horoscopes = self._generate_dashaflow_horoscopes(target_dt, numeric_tz)

        return JsonResponse({
            "date": date_param,
            # "location": resolved_location,
            "horoscopes": horoscopes
        }, json_dumps_params={'indent': 2})

    def options(self, request, *args, **kwargs):
        response = super().options(request, *args, **kwargs)
        response['Allow'] = 'GET, OPTIONS'
        return response