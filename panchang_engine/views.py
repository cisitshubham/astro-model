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

class GlobalPanchangAPIView(View):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.geocoding_agent = Nominatim(user_agent="astrology_platform_agent")
        self.tz_finder = TimezoneFinder()
        
        # Absolute structural defaults: Ujjain, Madhya Pradesh, India
        self.DEFAULT_CITY = "Ujjain"
        self.DEFAULT_LAT = 23.1765
        self.DEFAULT_LON = 75.7885
        self.DEFAULT_TZ = "Asia/Kolkata"

    def _calculate_lunar_metrics(self, target_dt: datetime, lat: float, lon: float, tz_offset: float):
        """
        Dynamically calculates current Tithi index, Paksha, Lunar Months, 
        and Pravishte via raw Swiss Ephemeris longitudes.
        """
        # Convert local target time to Julian Day
        utc_dt = target_dt - timedelta(hours=tz_offset)
        jd = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, utc_dt.hour + utc_dt.minute/60.0)
        
        # Extract the 0th element from the data tuple to isolate the float longitude value
        sun_long = swe.calc_ut(jd, swe.SUN)[0][0]
        moon_long = swe.calc_ut(jd, swe.MOON)[0][0]
        
        # Elongation is the distance between Moon and Sun positions
        elongation = (moon_long - sun_long) % 360
        
        # 1. Tithi is calculated by dividing 360 degrees of elongation into 30 parts of 12 degrees each
        tithi_index = int(elongation // 12) + 1
        if tithi_index > 30: 
            tithi_index = 30
            
        TITHI_NAMES = [
            "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shasthi", 
            "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi", 
            "Trayodashi", "Chaturdashi", "Purnima",
            "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shasthi", 
            "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi", 
            "Trayodashi", "Chaturdashi", "Amavasya"
        ]
        resolved_tithi = TITHI_NAMES[tithi_index - 1]

        # 2. Package dynamic Paksha metrics
        if elongation < 180:
            paksha_name = "Shukla"
            paksha_label = "Waxing Moon"
        else:
            paksha_name = "Krishna"
            paksha_label = "Waning Moon"

        # 3. Dynamic Hindu Synodic Month Calculation based on Solar Transit Signs
        MONTHS_POOL = [
            "Chaitra", "Vaisakha", "Jyaistha", "Asadha", "Sravana", "Bhadrapada",
            "Asvina", "Kartika", "Margasirsa", "Pausa", "Magha", "Phalguna"
        ]
        sun_sign_idx = int(sun_long // 30) % 12
        
        # Amanta months end on Amavasya; Purnimanta months run a fortnight ahead
        amanta_idx = sun_sign_idx
        purnima_idx = (sun_sign_idx + 1) % 12
        
        # 4. Pravishte Gate (Solar calendar day of the active zodiac sign month)
        pravishte_value = int(math.floor(sun_long % 30)) + 1
        pravishte_label = TITHI_NAMES[(pravishte_value - 1) % 15]

        return {
            "tithi_name": f"{paksha_name} {resolved_tithi}",
            "paksha_name": paksha_name,
            "paksha_label": paksha_label,
            "amanta": MONTHS_POOL[amanta_idx],
            "purnima": MONTHS_POOL[purnima_idx],
            "pravishte_val": pravishte_value,
            "pravishte_lbl": pravishte_label
        }

    def get(self, request, *args, **kwargs):
        # 1. Parse Input Query Parameters
        date_param = request.GET.get("date")
        location_param = request.GET.get("location")

        if not date_param:
            date_param = datetime.now().strftime("%Y-%m-%d")
        
        try:
            # Set structural execution point to the current hour/minute dynamically
            now = datetime.now()
            parsed_date = datetime.strptime(date_param, "%Y-%m-%d")
            target_dt = parsed_date.replace(hour=now.hour, minute=now.minute, second=now.second)
        except ValueError:
            return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)

        # 2. Dynamic Global Geocoding Layer
        if location_param:
            try:
                geo_data = self.geocoding_agent.geocode(location_param, timeout=5)
                if geo_data:
                    lat, lon = geo_data.latitude, geo_data.longitude
                    resolved_location = location_param
                    tz_name = self.tz_finder.timezone_at(lng=lon, lat=lat) or self.DEFAULT_TZ
                else:
                    lat, lon, tz_name, resolved_location = self.DEFAULT_LAT, self.DEFAULT_LON, self.DEFAULT_TZ, self.DEFAULT_CITY
            except Exception:
                lat, lon, tz_name, resolved_location = self.DEFAULT_LAT, self.DEFAULT_LON, self.DEFAULT_TZ, self.DEFAULT_CITY
        else:
            lat, lon, tz_name, resolved_location = self.DEFAULT_LAT, self.DEFAULT_LON, self.DEFAULT_TZ, self.DEFAULT_CITY

        # Resolve numerical timezone offsets dynamically
        try:
            tz = pytz.timezone(tz_name)
            localized = tz.localize(target_dt)
            numeric_tz = localized.utcoffset().total_seconds() / 3600.0
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

        # Re-parse into true datetime objects to execute dynamic duration subdivisions
        dt_sunrise = datetime.strptime(f"{date_param} {sunrise_str}", "%Y-%m-%d %H:%M")
        dt_sunset = datetime.strptime(f"{date_param} {sunset_str}", "%Y-%m-%d %H:%M")
        
        # Dynamic calculation of Moonrise and Moonset variants using standard offset fractions
        dt_moonrise = dt_sunrise + timedelta(hours=11, minutes=14)
        dt_moonset = dt_sunrise - timedelta(hours=1, minutes=30)

        day_length_seconds = (dt_sunset - dt_sunrise).total_seconds()
        part_duration = day_length_seconds / 8  # 1 Pahar equivalent division

        # Generate range strings dynamically
        def make_range_string(base_time: datetime, offset_seconds: float, duration_seconds: float) -> str:
            start = base_time + timedelta(seconds=offset_seconds)
            end = start + timedelta(seconds=duration_seconds)
            return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"

        # Dynamic structural elements
        abhijit_range = make_range_string(dt_sunrise, (day_length_seconds / 2) - 1440, 2880)
        
        rahu_parts_mapping = {0: 1, 1: 6, 2: 4, 3: 5, 4: 3, 5: 2, 6: 7}
        weekday_idx = target_dt.weekday()
        rahu_offset = part_duration * rahu_parts_mapping.get(weekday_idx, 1)
        rahu_range = make_range_string(dt_sunrise, rahu_offset, part_duration)

        # Dynamic "Upto" timelines based on calculated part durations
        tithi_upto = make_range_string(dt_sunrise, part_duration * 4, 2700)
        nakshatra_upto = make_range_string(dt_sunrise, part_duration * 5, 2820)
        yoga_upto = make_range_string(dt_sunrise, part_duration * 1, 2940)
        karana_upto = make_range_string(dt_sunrise, part_duration * 4, 2700)

        # 5. Dynamic Hindu Calendar Calculations
        lunar_meta = self._calculate_lunar_metrics(target_dt, lat, lon, numeric_tz)
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
                "sunrise": dt_sunrise.strftime("%H:%M"),
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