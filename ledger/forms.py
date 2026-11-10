from django import forms
from django.utils import timezone

from ledger.models import LedgerCategory, Record


class RecordForm(forms.ModelForm):
    class Meta:
        model = Record
        fields = ["category", "amount", "note", "record_date"]
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
            "note": forms.TextInput(attrs={"class": "form-control", "maxlength": "200"}),
            "record_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
        }
        labels = {"category": "分类", "amount": "金额", "note": "备注", "record_date": "日期"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = LedgerCategory.objects.all()
        if self.instance and self.instance.pk:
            self.initial["record_date"] = self.instance.record_date.strftime("%Y-%m-%d")
        else:
            self.initial["record_date"] = timezone.localdate().strftime("%Y-%m-%d")
