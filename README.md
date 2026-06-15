# Panchang API Engine (Dockerized Django + Swiss Ephemeris)

A high-performance Django-based astrological engine that delivers real-time, 100% dynamic Hindu calendrical metrics (Panchang) for any location worldwide. 

By leveraging the **Swiss Ephemeris (`swisseph`)** library and advanced astronomical calculations, this API computes daily planetary patterns, sunrise/sunset variations, time-segment sub-divisions (like Rahu Kaal and Abhijit Muhurat), and true lunar elongation values on the fly—completely eliminating hardcoded or static placeholders.

## Features

* **Global Geocoding & Timezone Tracking:** Dynamically resolves coordinates and local time zone offsets for any city worldwide using `geopy` and `timezonefinder`.
* **Zero Static Data:** Every metric—including Tithi, Paksha, Sun/Moon signs, and structural time limits ("upto" ranges)—is computed dynamically based on real-time ephemeris calculations.
* **Smart Fallback Matrix:** If no location parameter is provided or resolved, the API seamlessly falls back to calculations centered on **Ujjain, India** (the historical prime meridian of Hindu astronomy).
* **Docker Ready:** Production-ready `Dockerfile` and `docker-compose.yml` pre-configured to work with Traefik routing.

---

## Installation & Setup

### Using Docker (Recommended)

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd astro-model
   ```

2. **Set up Environment Variables:**
   Create a `.env` file in the root directory:
   ```env
   DEBUG=False
   SECRET_KEY=your_secret_key
   ALLOWED_HOSTS=engine.nakshatra.guru,localhost,127.0.0.1
   ```

3. **Start the application via Docker Compose:**
   ```bash
   docker compose up -d --build
   ```
   *This automatically runs migrations, collects static files, and starts the app with Gunicorn on port 8000.*

### Manual Local Setup (Virtual Environment)

1. **Install required dependencies:**
   Ensure your system has Python 3.10+ installed. Activate your virtual environment and run:
   ```bash
   pip install -r requirements.txt
   ```

2. **Apply Migrations:**
   ```bash
   python manage.py migrate
   ```

3. **Start the Development Server:**
   ```bash
   python manage.py runserver
   ```

---

## Testing the API Endpoint

Once running, you can test the Panchang API by visiting the endpoint.

**Example Request:**
```bash
curl "http://127.0.0.1:8000/api/panchang/?date=2026-06-15&location=Mumbai"
```

This will return a detailed JSON response featuring planetary placements, accurate astrological times, numerology metrics, and dynamically formatted Panchang data.ss