"""
forms.py

Mibs forms
"""

from typing import Any, Dict
from django import forms
from Mibs_widgets.widgets.Mibs_multi_select_field import MibsMultiSelectField


class MibsForm(forms.Form):
    def clean(self) -> Dict[str, Any]:
        for field_name, field_instance in self.fields.items():
            if isinstance(field_instance, MibsMultiSelectField):
                self.errors.pop(field_name, None)
                if len(self.data.getlist(field_name)) < 1:
                    raise forms.ValidationError({field_name: "This field is required"})
                cleaned_data = super().clean()
                employee_data = self.fields[field_name].queryset.filter(
                    id__in=self.data.getlist(field_name)
                )
                cleaned_data[field_name] = employee_data
        cleaned_data = super().clean()
        return cleaned_data


class MibsModelForm(forms.ModelForm):
    def clean(self) -> Dict[str, Any]:
        for field_name, field_instance in self.fields.items():
            if isinstance(field_instance, MibsMultiSelectField):
                self.errors.pop(field_name, None)
                if len(self.data.getlist(field_name)) < 1:
                    raise forms.ValidationError({field_name: "Thif field is required"})
                cleaned_data = super().clean()
                employee_data = self.fields[field_name].queryset.filter(
                    id__in=self.data.getlist(field_name)
                )
                cleaned_data[field_name] = employee_data
        cleaned_data = super().clean()
        return cleaned_data
