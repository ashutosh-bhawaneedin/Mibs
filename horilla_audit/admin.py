"""
admin.py
"""

from django.contrib import admin
from Mibs_audit.models import MibsAuditLog, MibsAuditInfo, AuditTag

# Register your models here.

admin.site.register(AuditTag)
