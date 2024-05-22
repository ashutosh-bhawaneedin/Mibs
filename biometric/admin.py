from django.contrib import admin
from .models import BiometricDevices, BiometricEmployees

# Register your models here.
admin.site.register(BiometricDevices)
admin.site.register(BiometricEmployees)
