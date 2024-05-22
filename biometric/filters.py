import django_filters
from base.filters import FilterSet
from biometric.models import BiometricDevices


class BiometricDeviceFilter(FilterSet):
    search = django_filters.CharFilter(field_name="name", lookup_expr="icontains")

    class Meta:
        """
        Meta class to add additional options
        """

        model = BiometricDevices
        fields = [
            "name",
            "machine_type",
            "is_active",
            "is_scheduler",
            "is_live",
        ]
