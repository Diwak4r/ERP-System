from __future__ import annotations

from datetime import date
from typing import Optional

from django import forms

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class ProductionEntryForm(forms.ModelForm):
    def __init__(self, *args, section: Optional[Section] = None, entry_date: Optional[date] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.fields["worker"].queryset = Worker.objects.filter(is_active=True)
        self.fields["item"].queryset = Item.objects.filter(is_active=True)
        if section:
            self.fields["worker"].label = f"Worker ({section})"
            self.fields["item"].label = f"Item ({section})"

    class Meta:
        model = ProductionEntry
        fields = ["worker", "item", "target_qty", "actual_qty", "shift_hours"]
        widgets = {
            "target_qty": forms.NumberInput(attrs={"readonly": True, "step": "0.01"}),
            "actual_qty": forms.NumberInput(attrs={"step": "0.01"}),
            "shift_hours": forms.NumberInput(attrs={"step": "0.25"}),
        }

    def _hydrate_targets(self) -> None:
        if not self.section or not self.entry_date or not self.cleaned_data.get("item"):
            return
        rule = (
            TargetRule.objects.for_section_item_date(section=self.section, item=self.cleaned_data["item"], target_date=self.entry_date)
            .first()
        )
        if rule:
            self.cleaned_data["target_qty"] = rule.target_qty
            self.cleaned_data["shift_hours"] = rule.shift_hours
        else:
            # No rule found, default to zero
            self.cleaned_data["target_qty"] = self.cleaned_data.get("target_qty") or 0
            self.cleaned_data["shift_hours"] = self.cleaned_data.get("shift_hours") or 0

    def clean(self):
        cleaned = super().clean()
        self._hydrate_targets()
        return cleaned


ProductionEntryFormSet = forms.formset_factory(ProductionEntryForm, extra=0, min_num=1, validate_min=True)
