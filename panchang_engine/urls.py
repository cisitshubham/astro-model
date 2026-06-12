from django.urls import path
# Change 'panchang_api' to 'GlobalPanchangAPIView'
from .views import GlobalPanchangAPIView 

urlpatterns = [
    # Class-based views need .as_view() called on them
    path('api/panchang/', GlobalPanchangAPIView.as_view(), name='global_panchang_api'),
]