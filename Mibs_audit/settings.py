"""
Mibs_audit/settings.py

This module is used to write settings contents related to payroll app
"""

from Mibs.settings import TEMPLATES

TEMPLATES[0]["OPTIONS"]["context_processors"].append(
    "Mibs_audit.context_processors.history_form",
)
