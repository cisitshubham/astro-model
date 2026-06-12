from datetime import datetime, timedelta
import swisseph as swe
import pytz
import random

# Attempt imports gracefully; provide mock fallback for environments without dashaflow installed
try:
    from dashaflow import cast_chart
except ImportError:
    def cast_chart(*args, **kwargs):
        return {}

class EphemerisComputationalEngine:
    def __init__(self):
        self.DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        self.ZODIAC_SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
        
        self.ELEMENT_MAPPING = {
            "Aries": "Fire", "Leo": "Fire", "Sagittarius": "Fire",
            "Taurus": "Earth", "Virgo": "Earth", "Capricorn": "Earth",
            "Gemini": "Air", "Libra": "Air", "Aquarius": "Air",
            "Cancer": "Water", "Scorpio": "Water", "Pisces": "Water"
        }

        self.PLANETARY_VIBES = {
            "Sun": "Sovereign", "Moon": "Intuitive", "Mercury": "Intellectual",
            "Venus": "Magnetic", "Mars": "Compassionate", "Jupiter": "Counsel",
            "Saturn": "Structuring", "Rahu": "Innovative", "Ketu": "Analytical",
            "Neptune": "Mystical", "Uranus": "Revolutionary", "Pluto": "Transformative"
        }

        self.ASPECT_THEMES = {
            "conjunction": "intensified focal alignment",
            "sextile": "opportunistic workflow flow",
            "square": "friction and structural testing",
            "trine": "creativity and romance",
            "opposition": "polarized awareness and balance"
        }

    def _decimal_to_degrees_minutes(self, decimal_deg: float) -> str:
        """Converts decimal floating longitudes safely into UI-compliant XX°XX' strings."""
        degrees = int(decimal_deg)
        minutes = int(round((decimal_deg - degrees) * 60))
        if minutes == 60:
            degrees += 1
            minutes = 0
        return f"{degrees}°{minutes:02d}'"

    def _get_sunrise_sunset(self, target_date: datetime, lat: float, lon: float, tz_offset: float):
        """Calculates exact sunrise and sunset times using Swiss Ephemeris."""
        try:
            utc_date = target_date - timedelta(hours=tz_offset)
            tjd = swe.julday(utc_date.year, utc_date.month, utc_date.day, 0.0)
            geopos = [lon, lat, 0.0]
            
            res_rise = swe.rise_trans(tjd, swe.SUN, geopos, ephe_flag=swe.FLG_SWIEPH, rsmi=swe.BIT_DISC_CENTER | swe.BIT_CALC_RISE)
            res_set = swe.rise_trans(tjd, swe.SUN, geopos, ephe_flag=swe.FLG_SWIEPH, rsmi=swe.BIT_DISC_CENTER | swe.BIT_CALC_SET)
            
            def jd_to_local(jd):
                ymd_hms = swe.revjul(jd)
                dec_hour = ymd_hms[3]
                hours = int(dec_hour)
                minutes = int((dec_hour - hours) * 60)
                utc_dt = datetime(ymd_hms[0], ymd_hms[1], ymd_hms[2], hours, minutes)
                return utc_dt + timedelta(hours=tz_offset)

            return jd_to_local(res_rise[1][0]), jd_to_local(res_set[1][0])
        except Exception:
            base_sunrise = datetime(target_date.year, target_date.month, target_date.day, 5, 30)
            base_sunset = datetime(target_date.year, target_date.month, target_date.day, 19, 15)
            return base_sunrise, base_sunset

    def _extract_raw_longitude(self, body_data) -> float:
        """Safely scans across all potential payload schemas to pull true decimal longitude."""
        if isinstance(body_data, (int, float)):
            return float(body_data)
        if isinstance(body_data, dict):
            for key in ["longitude", "degrees", "degree", "lon", "position", "value"]:
                if key in body_data:
                    return float(body_data[key])
        return None

    def _fallback_extract_sign(self, chart_data, target_key):
        """Deep scanning routine to safely recover sign designations from unpredictable nested structures."""
        search_keys = [target_key, target_key.lower(), f"{target_key}_sign", f"{target_key}Sign"]
        
        # Level 1: Look inside nested Panchang blocks
        panchang_block = chart_data.get('panchang') or chart_data.get('Panchang') or {}
        if isinstance(panchang_block, dict):
            for sk in search_keys:
                if sk in panchang_block:
                    val = panchang_block[sk]
                    return val.get('name') if isinstance(val, dict) else val

        # Level 2: Look inside nested Planets blocks
        planets_block = chart_data.get('planets') or chart_data.get('Planets') or {}
        if isinstance(planets_block, dict):
            for sk in search_keys:
                if sk in planets_block:
                    val = planets_block[sk]
                    if isinstance(val, dict):
                        return val.get('sign') or val.get('Sign') or val.get('name')
                    return val

        # Level 3: Look at the absolute root layout
        for sk in search_keys:
            if sk in chart_data:
                val = chart_data[sk]
                return val.get('name') if isinstance(val, dict) else val

        return "Unknown"

    def get_panchang_data(self, target_date: datetime, lat: float, lon: float, timezone_str: str) -> dict:
        """Processes Panchang, Rahu Kaal, Abhijit Muhurat, and full Celestial Position matrices."""
        dob_str = target_date.strftime('%Y-%m-%d')
        time_str = target_date.strftime('%H:%M')
        
        yesterday_date = target_date - timedelta(days=1)
        yesterday_dob_str = yesterday_date.strftime('%Y-%m-%d')
        
        try:
            tz = pytz.timezone(timezone_str)
            localized = tz.localize(target_date)
            numeric_tz = localized.utcoffset().total_seconds() / 3600.0
        except Exception:
            numeric_tz = 5.5
            timezone_str = "Asia/Kolkata"
            
        chart_data = cast_chart(dob=dob_str, time=time_str, lat=lat, lon=lon, timezone=timezone_str) or {}
        yesterday_chart_data = cast_chart(dob=yesterday_dob_str, time=time_str, lat=lat, lon=lon, timezone=timezone_str) or {}
        
        panchang = chart_data.get('panchang') or chart_data.get('Panchang') or {}
        planets = chart_data.get('planets') or chart_data.get('Planets') or {}
        yesterday_planets = yesterday_chart_data.get('planets') or yesterday_chart_data.get('Planets') or {}
        
        sunrise, sunset = self._get_sunrise_sunset(target_date, lat, lon, numeric_tz)
        daytime_duration = sunset - sunrise
        part_duration = daytime_duration / 8
        
        rahu_parts_mapping = {0: 1, 1: 6, 2: 4, 3: 5, 4: 3, 5: 2, 6: 7}
        weekday_idx = target_date.weekday()
        rahu_start = sunrise + (part_duration * rahu_parts_mapping.get(weekday_idx, 1))
        rahu_end = rahu_start + part_duration
        
        midday = sunrise + (daytime_duration / 2)
        abhijit_start = midday - timedelta(minutes=24)
        abhijit_end = midday + timedelta(minutes=24)

        target_bodies = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Rahu", "Ketu", "Neptune", "Uranus", "Pluto"]
        celestial_planets_matrix = {}
        daily_transits_log = []

        for body in target_bodies:
            body_data = planets.get(body) or planets.get(body.lower()) or {}
            yest_body_data = yesterday_planets.get(body) or yesterday_planets.get(body.lower()) or {}
            
            raw_degrees = self._extract_raw_longitude(body_data)
            yest_degrees = self._extract_raw_longitude(yest_body_data)
            
            if raw_degrees is not None:
                sign_index = int(raw_degrees // 30) % 12
                sign_name = body_data.get("sign") or body_data.get("Sign") or self.ZODIAC_SIGNS[sign_index]
                
                is_retrograde = body_data.get("retrograde", body_data.get("is_retrograde", False))
                nakshatra_name = body_data.get("nakshatra") or body_data.get("Nakshatra") or "Unknown"
                status_profile = body_data.get("status") or "normal"

                active_element = self.ELEMENT_MAPPING.get(sign_name, "Fire")
                motion_status = "RETROGRADE" if is_retrograde else "DIRECT"
                formatted_coordinates = self._decimal_to_degrees_minutes(raw_degrees % 30)
                base_vibe = self.PLANETARY_VIBES.get(body, "Cosmic")

                celestial_planets_matrix[body.lower()] = {
                    "name": body,
                    "abs_longitude": raw_degrees,
                    "sign_resolved": sign_name,
                    "ui_title": f"The {body}",
                    "ruler_element": f"{sign_name} · {active_element} element",
                    "energy_signature": f"{base_vibe} energy",
                    "meta_data": {
                        "formatted_degrees": formatted_coordinates,
                        "motion_status": motion_status,
                        "nakshatra": nakshatra_name,
                        "status_layer": status_profile
                    }
                }

                if yest_degrees is not None:
                    yest_sign_index = int(yest_degrees // 30) % 12
                    if sign_index != yest_sign_index:
                        daily_transits_log.append({
                            "event_type": "INGRESS",
                            "title": f"{body} enters {sign_name}",
                            "intensity": "HIGH"
                        })

        def parse_panchang_element(payload, element_key):
            target = payload.get(element_key) or payload.get(element_key.lower())
            if isinstance(target, dict):
                return target.get("name") or target.get("value") or "N/A"
            return target if target else "N/A"

        # Apply multi-layer recovery strategy for Sun & Moon signs
        derived_sun = celestial_planets_matrix.get('sun', {}).get('sign_resolved')
        if not derived_sun:
            derived_sun = self._fallback_extract_sign(chart_data, "sun")

        derived_moon = celestial_planets_matrix.get('moon', {}).get('sign_resolved')
        if not derived_moon:
            derived_moon = self._fallback_extract_sign(chart_data, "moon")

        # return {
        #     "sun_sign": derived_sun,
        #     "moon_sign": derived_moon,
        #     "tithi": parse_panchang_element(panchang, "Tithi"),
        #     "nakshatra": parse_panchang_element(panchang, "Nakshatra"),
        #     "vara": parse_panchang_element(panchang, "Vara") if parse_panchang_element(panchang, "Vara") != "N/A" else self.DAYS[weekday_idx],
        #     "paksha": parse_panchang_element(panchang, "Paksha"),
        #     "yoga": parse_panchang_element(panchang, "Yoga"),
        #     "karana": parse_panchang_element(panchang, "Karana"),
        #     "sunrise": sunrise.strftime('%I:%M %p'),
        #     "sunset": sunset.strftime('%I:%M %p'),
        #     "abhijit_muhurat": f"{abhijit_start.strftime('%I:%M %p')} to {abhijit_end.strftime('%I:%M %p')}",
        #     "rahu_kaal": f"{rahu_start.strftime('%I:%M %p')} to {rahu_end.strftime('%I:%M %p')}",
        #     "celestial_planets_matrix": celestial_planets_matrix,
        #     "astrological_transits": daily_transits_log
        # }
        panchang_payload = {
            "date": target_date.strftime("%Y-%m-%d"),
            "location": {
                "latitude": lat,
                "longitude": lon,
                "timezone": timezone_str
            },
            "panchang": {
                "sun_sign": derived_sun,
                "moon_sign": derived_moon,
                "vara": parse_panchang_element(panchang, "Vara")
                    if parse_panchang_element(panchang, "Vara") != "N/A"
                    else self.DAYS[weekday_idx],
                "tithi": parse_panchang_element(panchang, "Tithi"),
                "nakshatra": parse_panchang_element(panchang, "Nakshatra"),
                "paksha": parse_panchang_element(panchang, "Paksha"),
                "yoga": parse_panchang_element(panchang, "Yoga"),
                "karana": parse_panchang_element(panchang, "Karana")
            },
            "timings": {
                "sunrise": sunrise.strftime("%I:%M %p"),
                "sunset": sunset.strftime("%I:%M %p"),
                "abhijit_muhurat": f"{abhijit_start.strftime('%I:%M %p')} to {abhijit_end.strftime('%I:%M %p')}",
                "rahu_kaal": f"{rahu_start.strftime('%I:%M %p')} to {rahu_end.strftime('%I:%M %p')}"
            },
            "planets": celestial_planets_matrix,
            "transits": daily_transits_log
        }

        return panchang_payload


class NumerologyComputationalEngine:
    CORE_UI_NAMES = ["LEADER", "DIPLOMAT", "CREATOR", "BUILDER", "EXPLORER", "NURTURER", "SEEKER", "ACHIEVER", "VISIONARY"]
    ELEMENTS_POOL = ["Fire", "Water", "Air", "Earth"]
    
    TRAIT_DESCRIPTOR_POOL = [
        ["Pioneering", "Assertive", "Independent"],
        ["Harmonious", "Empathetic", "Diplomatic"],
        ["Imaginative", "Expressive", "Artistic"],
        ["Methodical", "Pragmatic", "Grounded"],
        ["Dynamic", "Resourceful", "Versatile"],
        ["Compassionate", "Sustaining", "Humanitarian"],
        ["Analytical", "Strategic", "Metaphysical"],
        ["Ambitious", "Resilient", "Authoritative"],
        ["Idealistic", "Philanthropic", "Universal"]
    ]

    def _reduce_to_single_digit(self, number: int) -> int:
        while number > 9:
            number = sum(int(digit) for digit in str(number))
        return number

    def calculate_numerology_profile(self, target_date: datetime, lat: float, lon: float, timezone_str: str) -> dict:
        day, month, year = target_date.day, target_date.month, target_date.year

        ephemeris = EphemerisComputationalEngine()
        panchang_data = ephemeris.get_panchang_data(target_date, lat, lon, timezone_str)
        
        current_sun_sign = panchang_data.get('sun_sign', 'Unknown')
        current_moon_sign = panchang_data.get('moon_sign', 'Unknown')
        active_nakshatra = panchang_data.get('nakshatra', 'Unknown')
        
        planets_matrix = panchang_data.get('celestial_planets_matrix', {})
        transit_ruler_sign = planets_matrix.get('mars', {}).get('sign_resolved', 'Unknown')

        universal_seed = self._reduce_to_single_digit(day + month + year)
        matrix_payload = {
            "date": target_date.strftime('%Y-%m-%d'),
            "universal_vibration": universal_seed,
            "profiles": {}
        }

        for base_num in range(1, 10):
            personal_day = self._reduce_to_single_digit(base_num + day + month)
            title_index = (base_num - 1 + day) % 9
            element_index = (personal_day + month) % 4
            trait_index = (base_num - 1 + universal_seed) % 9

            active_title = f"The {self.CORE_UI_NAMES[title_index].capitalize()}"
            active_element = self.ELEMENTS_POOL[element_index]
            active_traits = self.TRAIT_DESCRIPTOR_POOL[trait_index]
            
            if self.CORE_UI_NAMES[title_index] == "VISIONARY":
                energy_signature = "Compassionate energy"
                core_description = "Compassionate and humanitarian, this number is driven by a desire to improve global framework conditions."
                dynamic_reading = (
                    f"Compassionate and humanitarian, this number is driven by a desire to make the world a better place. "
                    f"At this matrix coordinates point, you intersect with a sun sign pattern of {current_sun_sign} and "
                    f"lunar field shifts across {current_moon_sign} within the nakshatra of {active_nakshatra}."
                )
                active_traits = ["Idealistic", "Humanitarian", "Giving"]
            else:
                energy_signature = f"{active_traits[0]} energy"
                core_description = f"{active_traits[0]} and {active_traits[1].lower()}, this number is driven by a desire to optimize daily execution paths."
                dynamic_reading = (
                    f"{active_traits[0]} and {active_traits[1].lower()}, this number is driven by a desire to optimize "
                    f"daily execution paths. Under your active profile configuration, your matrix processes an internal "
                    f"Personal Day Vector of {personal_day}. This parameters-set intersects with a solar transit of {current_sun_sign} "
                    f"and a lunar sweep through {current_moon_sign} within the nakshatra of {active_nakshatra}. These alignments heavily "
                    f"activate your temporary {active_element.lower()} processing parameters."
                )

            matrix_payload["profiles"][base_num] = {
                "title": active_title,
                "ruler_element": f"{transit_ruler_sign} · {active_element} element",
                "energy_signature": energy_signature,
                "description": core_description,
                "todays_reading": dynamic_reading,
                "key_traits": active_traits
            }

        return matrix_payload


if __name__ == "__main__":
    # Test initialization vector
    engine = EphemerisComputationalEngine()
    num_engine = NumerologyComputationalEngine()
    
    # Configuration arguments (New Delhi)
    test_time = datetime.now()
    latitude, longitude = 28.6139, 77.2090
    local_tz = "Asia/Kolkata"
    
    panchang_output = engine.get_panchang_data(test_time, latitude, longitude, local_tz)
    
    print("=" * 50)
    print("        DAILY PANCHANG ENGINE METRICS        ")
    print("=" * 50)
    print(f" Day (Vara)   : {panchang_output['vara']}")
    print(f" Paksha       : {panchang_output['paksha']}")
    print(f" Tithi        : {panchang_output['tithi']}")
    print(f" Nakshatra    : {panchang_output['nakshatra']}")
    print(f" Yoga         : {panchang_output['yoga']}")
    print(f" Karana       : {panchang_output['karana']}")
    print("-" * 50)
    print(f" Sun Sign     : {panchang_output['sun_sign']}")
    print(f" Moon Sign    : {panchang_output['moon_sign']}")
    print("-" * 50)
    print(f" Sunrise      : {panchang_output['sunrise']}")
    print(f" Sunset       : {panchang_output['sunset']}")
    print(f" Abhijit Muh. : {panchang_output['abhijit_muhurat']}")
    print(f" Rahu Kaal    : {panchang_output['rahu_kaal']}")
    print("=" * 50)