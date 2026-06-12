import sys
from datetime import datetime
from django.core.management.base import BaseCommand
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

# Import your dynamic backend computation layers
from panchang_engine.engine import EphemerisComputationalEngine, NumerologyComputationalEngine


class Command(BaseCommand):
    help = 'Interactive terminal control panel for Panchang, Horoscopes, Numerology, Transits, and Celestial alignments.'

    def handle(self, *args, **options):
        # Initialize engines
        engine = EphemerisComputationalEngine()
        numerology_engine = NumerologyComputationalEngine()

        while True:
            self.stdout.write("\n=========================================================================")
            self.stdout.write(self.style.SUCCESS("             ASTRO-NUMEROLOGY INTERACTIVE CONTROL PANEL                  "))
            self.stdout.write("=========================================================================")
            self.stdout.write(" [1] Daily Horoscopes       (Requires: Date Only)")
            self.stdout.write(" [2] Numerology Profiles    (Requires: Date Only)")
            self.stdout.write(" [3] Complete Panchang     (Requires: Date & City)")
            self.stdout.write(" [4] Transit Alerts Feed    (Requires: Date & City)")
            self.stdout.write(" [5] Live Celestial Matrix  (Requires: Date & City)")
            self.stdout.write(" [6] Exit Application")
            self.stdout.write("=========================================================================")
            
            try:
                choice = input("Select an option (1-6): ").strip()
            except (KeyboardInterrupt, EOFError):
                self.stdout.write(self.style.WARNING("\n\nExecution terminated. Goodbye!"))
                sys.exit(0)

            if choice == '6':
                self.stdout.write(self.style.SUCCESS("Closing control panel. Goodbye!"))
                break

            if choice not in ['1', '2', '3', '4', '5']:
                self.stdout.write(self.style.ERROR("Invalid selection. Please enter a digit between 1 and 6."))
                continue

            # --- STEP 1: CAPTURE DATE (Required for ALL options) ---
            parsed_date = None
            while not parsed_date:
                date_str = input("Enter Date (YYYY-MM-DD) [or press Enter for Today]: ").strip()
                if not date_str:
                    parsed_date = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
                    break
                try:
                    parsed_date = datetime.strptime(f"{date_str} 12:00", "%Y-%m-%d %H:%M")
                except ValueError:
                    self.stdout.write(self.style.ERROR("Invalid formatting structure. Please use YYYY-MM-DD."))

            # Default fallback coordinates for date-only engines (if inner methods require them)
            lat, lon = 30.9010, 75.8573
            iana_tz = "Asia/Kolkata"

            # --- STEP 2: CONDITIONALLY CAPTURE CITY (Only for options 3, 4, 5) ---
            if choice in ['3', '4', '5']:
                resolved = False
                while not resolved:
                    city_name = input("Enter City Name: ").strip()
                    if not city_name:
                        self.stdout.write(self.style.ERROR("City name cannot be empty for celestial calculations."))
                        continue
                    
                    self.stdout.write(f"Resolving coordinates for '{city_name}'...")
                    geolocator = Nominatim(user_agent="panchang_engine_locator")
                    location = geolocator.geocode(city_name)

                    if not location:
                        self.stdout.write(self.style.ERROR(f"Could not locate '{city_name}'. Try again."))
                        continue
                    
                    lat, lon = location.latitude, location.longitude
                    tf = TimezoneFinder()
                    iana_tz = tf.timezone_at(lng=lon, lat=lat) or "Asia/Kolkata"
                    
                    self.stdout.write(self.style.SUCCESS(f"Resolved: {location.address} ({iana_tz})"))
                    resolved = True

            # --- STEP 3: EXECUTE SELECTED ENGINE OPERATION ---
            self.stdout.write("\nProcessing operational matrices... Standby.\n")

            # Option 1: Daily Horoscopes (Date Only)
            if choice == '1':
                self.stdout.write("=========================================================================")
                self.stdout.write(self.style.SUCCESS(f"         DAILY HOROSCOPES FOR ALL 12 SIGNS ({parsed_date.strftime('%Y-%m-%d')})         "))
                self.stdout.write("=========================================================================")
                horoscopes = engine.get_daily_horoscopes(parsed_date, lat, lon, iana_tz)
                for sign, payload in horoscopes.items():
                    self.stdout.write(self.style.NOTICE(f"{payload['ui_title'].upper()}"))
                    self.stdout.write(f"  {payload['prediction']}")
                    self.stdout.write("-" * 73)

            # Option 2: Numerology Profiles (Date Only)
            elif choice == '2':
                self.stdout.write("=========================================================================")
                self.stdout.write(self.style.SUCCESS(f"          DYNAMIC INTERFACE NUMEROLOGY ENGINE ({parsed_date.strftime('%Y-%m-%d')})          "))
                self.stdout.write("=========================================================================")
                ui_matrix = numerology_engine.calculate_numerology_profile(parsed_date, lat, lon, iana_tz)
                for base_num, card_data in ui_matrix["profiles"].items():
                    self.stdout.write(self.style.NOTICE(f"\nROOT FREQUENCY PROFILE {base_num} : {card_data['title'].upper()}"))
                    self.stdout.write(f"  Configuration : {card_data['ruler_element']}")
                    self.stdout.write(f"  Signature     : {card_data['energy_signature']}")
                    self.stdout.write(f"  Description   : {card_data['description']}")
                    self.stdout.write(f"\n  Today's Reading:\n    {card_data['todays_reading']}")
                    self.stdout.write(f"\n  Dynamic Key Traits:")
                    for trait in card_data["key_traits"]:
                        self.stdout.write(f"    • {trait}")
                    self.stdout.write("-" * 73)

            # Option 3: Complete Panchang (Date & City)
            elif choice == '3':
                data = engine.get_panchang_data(parsed_date, lat, lon, iana_tz)
                self.stdout.write("=========================================")
                self.stdout.write(self.style.SUCCESS("         COMPLETE PANCHANG REPORT        "))
                self.stdout.write("=========================================")
                self.stdout.write(f"Vara (Weekday):   {data.get('vara')}")
                self.stdout.write(f"Tithi:            {data.get('tithi')}")
                self.stdout.write(f"Nakshatra:        {data.get('nakshatra')}")
                self.stdout.write(f"Yoga:             {data.get('yoga')}")
                self.stdout.write(f"Karana:           {data.get('karana')}")
                self.stdout.write("-----------------------------------------")
                self.stdout.write(f"Sun Sign:         {data.get('sun_sign')}")
                self.stdout.write(f"Moon Sign:        {data.get('moon_sign')}")
                self.stdout.write("-----------------------------------------")
                self.stdout.write(f"Sunrise:          {data.get('sunrise')}")
                self.stdout.write(f"Sunset:           {data.get('sunset')}")
                self.stdout.write("-----------------------------------------")
                self.stdout.write(self.style.WARNING(f"Rahu Kaal:        {data.get('rahu_kaal')} (Inauspicious)"))
                self.stdout.write(self.style.NOTICE(f"Abhijit Muhurat:  {data.get('abhijit_muhurat')} (Auspicious)"))
                self.stdout.write("=========================================\n")

            # Option 4: Transit Alerts Feed (Date & City)
            elif choice == '4':
                data = engine.get_panchang_data(parsed_date, lat, lon, iana_tz)
                transits_feed = data.get("astrological_transits", [])
                self.stdout.write("=========================================================================")
                self.stdout.write(self.style.SUCCESS("                PLANETARY TRANSIT TIMELINE FEED ALERTS                   "))
                self.stdout.write("=========================================================================")
                if not transits_feed:
                    self.stdout.write(" No significant planetary transits or aspects tracked for this window.")
                else:
                    for event in transits_feed:
                        style_func = self.style.SUCCESS if event["intensity"] == "VERY_HIGH" else (self.style.WARNING if event["intensity"] == "HIGH" else self.style.NOTICE)
                        tag_string = " · ".join(event["tags"])
                        self.stdout.write(style_func(f"● {event['title'].upper():<35}") + f" | Intensity: {event['intensity']:<9} | [{tag_string}]")
                        self.stdout.write(f"   Context: {event['subtitle']}")
                        self.stdout.write("-" * 73)

            # Option 5: Live Celestial Matrix (Date & City)
            elif choice == '5':
                data = engine.get_panchang_data(parsed_date, lat, lon, iana_tz)
                planets_matrix = data.get("celestial_planets_matrix", {})
                self.stdout.write("=========================================================================")
                self.stdout.write(self.style.SUCCESS("             LIVE CELESTIAL PLANETARY PLACEMENT MATRIX                   "))
                self.stdout.write("=========================================================================")
                for p_key, p_data in planets_matrix.items():
                    meta = p_data.get("meta_data", {})
                    motion_flag = f"[{meta.get('motion_status', 'DIRECT')}]"
                    self.stdout.write(self.style.NOTICE(f"● {p_data['name'].upper():<12}") + f"➔ {p_data['ruler_element']:<24} | Coord: {meta.get('formatted_degrees', '0°00\''):<8} | {motion_flag:<12}")
                    self.stdout.write(f"  Energy Signature : {p_data['energy_signature']}")
                    self.stdout.write(f"  Active Reading   : {p_data['todays_reading']}")
                    self.stdout.write("-" * 73)

            # Pause to keep output readable before returning to selection loop
            input("\nPress Enter to return to the Main Menu...")