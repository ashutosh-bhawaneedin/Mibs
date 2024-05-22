
from django.urls import path
from . import views
from .models import BiometricDevices
from attendance.views import clock_in_out

urlpatterns = [
path(
        "view-biometric-devices/",
        views.biometric_devices_view,
        name="view-biometric-devices",
    ),
    path(
        "biometric-device-live-capture",
        views.biometric_device_live,
        name="biometric-device-live-capture",
    ),
    path(
        "biometric-device-schedule/<uuid:device_id>/",
        views.biometric_device_schedule,
        name="biometric-device-schedule",
    ),
    path(
        "biometric-device-unschedule/<uuid:device_id>/",
        views.biometric_device_unschedule,
        name="biometric-device-unschedule",
    ),
    path(
        "biometric-device-test/<uuid:device_id>/",
        views.biometric_device_test,
        name="biometric-device-test",
    ),
    path(
        "biometric-device-add",
        views.biometric_device_add,
        name="biometric-device-add",
    ),
    path(
        "biometric-device-edit/<uuid:device_id>/",
        views.biometric_device_edit,
        name="biometric-device-edit",
    ),
    path(
        "biometric-device-delete/<uuid:device_id>/",
        views.biometric_device_delete,
        name="biometric-device-delete",
    ),
    path(
        "biometric-device-archive/<uuid:device_id>/",
        views.biometric_device_archive,
        name="biometric-device-archive",
    ),
    path(
        "search-devices",
        views.search_devices,
        name="search-devices",
    ),
    path(
        "biometric-device-employees/<uuid:device_id>/",
        views.biometric_device_employees,
        name="biometric-device-employees",
        kwargs={"model": BiometricDevices},
    ),
    path(
        "search-employee-in-device",
        views.search_employee_device,
        name="search-employee-in-device",
    ),
    path(
        "add-biometric-user/<uuid:device_id>/",
        views.add_biometric_user,
        name="add-biometric-user",
    ),
    path(
        "delete-biometric-user/<int:uid>/<uuid:device_id>/",
        views.delete_biometric_user,
        name="delete-biometric-user",
    ),
    path(
        "biometric-users-bulk-delete",
        views.bio_users_bulk_delete,
        name="biometric-users-bulk-delete",
    ),
]