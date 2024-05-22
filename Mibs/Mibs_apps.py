"""
Mibs_apps

This module is used to register Mibs addons
"""
from Mibs.settings import INSTALLED_APPS
from Mibs import settings

INSTALLED_APPS.append("Mibs_audit")
INSTALLED_APPS.append("Mibs_widgets")
INSTALLED_APPS.append("Mibs_crumbs")
INSTALLED_APPS.append("Mibs_documents")
INSTALLED_APPS.append("haystack")
INSTALLED_APPS.append("helpdesk")
INSTALLED_APPS.append("offboarding")
INSTALLED_APPS.append("biometric")

setattr(settings,"EMAIL_BACKEND","base.backends.ConfiguredEmailBackend")