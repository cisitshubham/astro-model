from django.urls import path
from .views import (
    GlobalPanchangAPIView, 
    GlobalTransitsAPIView, 
    GlobalCelestialAPIView,
    GlobalNumerologyAPIView,
    GlobalHoroscopeAPIView
)

urlpatterns = [
    # 1. Vedic Panchang Metrics (Sunrise, Sunset, Rahukal, Abhijit Moohrat, Tithi, etc.)
    path('api/panchang/', GlobalPanchangAPIView.as_view(), name='global_panchang_api'),
    
    # 2. Planetary Transit Events (Dynamic Ingress & Direction/Stationary Changes)
    path('api/transits/', GlobalTransitsAPIView.as_view(), name='global_transits_api'),
    
    # 3. Celestial Coordinate Tracking (Exact Signs, Raw Degrees, Retrograde Status, Nakshatras & Dignities)
    path('api/celestial/', GlobalCelestialAPIView.as_view(), name='global_celestial_api'),
    
    # 4. Pure Date-driven Numerology Matrix (Algorithmic 1-9 Daily Narrative Shuffler)
    path('api/numerology/', GlobalNumerologyAPIView.as_view(), name='global_numerology_api'),
    
    # 5 Horoscope
    path('api/horoscope/', GlobalHoroscopeAPIView.as_view(), name='global_horoscope_api'),
]