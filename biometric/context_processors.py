from base.models import BiometricAttendance


def biometric_is_installed(request):
    object = BiometricAttendance.objects.first()
    if not object:
        biometric_instance = BiometricAttendance.objects.create(is_installed=False)
        object = BiometricAttendance.objects.first()
    is_installed = object.is_installed
    return {"is_installed": is_installed}
