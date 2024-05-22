"""
Mibs_middlewares.py

This module is used to register Mibs's middlewares without affecting the Mibs/settings.py
"""

from Mibs.settings import MIDDLEWARE

MIDDLEWARE.append("base.middleware.CompanyMiddleware")
MIDDLEWARE.append("base.thread_local_middleware.ThreadLocalMiddleware")
