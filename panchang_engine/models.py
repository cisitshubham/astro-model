from django.db import models

class GlobalPanchangAlmanac(models.Model):
    requested_city = models.CharField(max_length=150, db_index=True)
    calculation_date = models.DateField(db_index=True)
    
    # --- NEW NUMEROLOGY INTEGRATION FIELDS ---
    psychic_number = models.IntegerField(default=1)
    destiny_number = models.IntegerField(default=1)
    numerology_destiny_ruler = models.CharField(max_length=50, default="Sun")

    class Meta:
        unique_together = ('calculation_date', 'requested_city')
    def __str__(self):
        return f"{self.requested_city} - {self.calculation_date}"
