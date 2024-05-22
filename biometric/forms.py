from django import forms
from django.utils.translation import gettext_lazy as _
from employee.models import Employee
from .models import BiometricDevices,BiometricEmployees
from attendance.forms import ModelForm 
from base.forms import Form




class BiometricDeviceForm(ModelForm):
    class Meta:
        model = BiometricDevices
        fields = "__all__"
        exclude = [
            "is_scheduler",
            "scheduler_duration",
            "is_active",
        ]
        labels = {
            "name": _("Device Name"),
            "machine_ip": _("IP Address"),
            "port": _("TCP COMM.Port"),
        }
        widgets = {
            "machine_type": forms.Select(
                attrs={
                    "id": "machineTypeInput",
                    "onchange": "machineTypeChange($(this))",
                }
            ),
        }


class BiometricDeviceSchedulerForm(ModelForm):
    class Meta:
        model = BiometricDevices
        fields = ["scheduler_duration"]
        labels = {
            "scheduler_duration": _("Enter the duration in the format HH:MM"),
        }


class EmployeeBiometricAddForm(Form):
    employee_ids = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.all(),
        widget=forms.SelectMultiple(),
        label=_("Employees"),
    )

    def __init__(self, *args, **kwargs):
        super(EmployeeBiometricAddForm, self).__init__(*args, **kwargs)

        biometric_employee_ids = BiometricEmployees.objects.values_list(
            "employee_id", flat=True
        )
        self.fields["employee_ids"].queryset = Employee.objects.exclude(
            id__in=biometric_employee_ids
        )
