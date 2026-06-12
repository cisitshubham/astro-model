from django.db import models

class GlobalPanchangAlmanac(models.Model):
    requested_city = models.CharField(max_length=150, db_index=True)
    resolved_country = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    iana_timezone = models.CharField(max_length=100)
    calculation_date = models.DateField(db_index=True)
    
    # Astronomical Windows
    sunrise = models.TimeField()
    sunset = models.TimeField()
    moonrise = models.CharField(max_length=50)
    moonset = models.CharField(max_length=50)
    
    # Planetary Structures
    sun_sign = models.CharField(max_length=50)
    moon_sign = models.CharField(max_length=50)
    
    # Custom Division Blocks
    abhijeet_muhurat_start = models.TimeField()
    abhijeet_muhurat_end = models.TimeField()
    rahu_kaal_start = models.TimeField()
    rahu_kaal_end = models.TimeField()
    
    # Calendar Eras Metadata
    shaka_samvat = models.IntegerField()
    vikram_samvat = models.IntegerField()
    var_day_name = models.CharField(max_length=20)
    paksha = models.CharField(max_length=20)
    ananta_month = models.CharField(max_length=50)
    purnima_month = models.CharField(max_length=50)
    pravisthe_gate = models.IntegerField()
    
    # Core Five Pillars Timeline Blobs
    tithi_timeline = models.CharField(max_length=150)
    nakshatra_timeline = models.CharField(max_length=150)
    yoga_timeline = models.CharField(max_length=150)
    karana_timeline = models.CharField(max_length=150)

    class Meta:
        unique_together = ('calculation_date', 'requested_city')
        indexes = [
            models.Index(fields=['calculation_date', 'requested_city'], name='idx_date_city_composite'),
        ]

    def __str__(self):
        return f"{self.requested_city} - {self.calculation_date}"
    
class GlobalPanchangAlmanac(models.Model):
    # ... keep all your existing fields exactly the same ...
    requested_city = models.CharField(max_length=150, db_index=True)
    calculation_date = models.DateField(db_index=True)
    
    # --- NEW NUMEROLOGY INTEGRATION FIELDS ---
    psychic_number = models.IntegerField(default=1)
    destiny_number = models.IntegerField(default=1)
    numerology_destiny_ruler = models.CharField(max_length=50, default="Sun")

    class Meta:
        unique_together = ('calculation_date', 'requested_city')    