from __future__ import annotations

from datetime import date
from typing import Optional

from django import forms

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class ProductionEntryForm(forms.ModelForm):
    def __init__(
        self,
        *args,
        section: Optional[Section] = None,
        entry_date: Optional[date] = None,
        workers_qs=None,
        items_qs=None,
        rules_map=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.rules_map = rules_map

        # Optimization: use pre-fetched querysets if provided
        self.fields["worker"].queryset = (
            workers_qs if workers_qs is not None else Worker.objects.filter(is_active=True)
        )
        self.fields["item"].queryset = items_qs if items_qs is not None else Item.objects.filter(is_active=True)

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
        item = self.cleaned_data.get("item")
        if not self.section or not self.entry_date or not item:
            return

        rule = None
        if self.rules_map is not None:
            # Optimization: use pre-fetched rules map
            rule = self.rules_map.get(item.id)
        else:
            rule = TargetRule.objects.for_section_item_date(
                section=self.section, item=item, target_date=self.entry_date
            ).first()

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


class BaseProductionEntryFormSet(forms.BaseFormSet):
    def __init__(self, *args, **kwargs):
        self.section = kwargs.get("form_kwargs", {}).get("section")
        self.entry_date = kwargs.get("form_kwargs", {}).get("entry_date")

        # Pre-fetch common data to avoid N+1 queries in forms
        self.workers_qs = Worker.objects.filter(is_active=True)
        self.items_qs = Item.objects.filter(is_active=True)
        self.rules_map = None

        if self.section and self.entry_date:
            # Fetch all applicable rules for the section/date at once
            rules = TargetRule.objects.for_section_item_date(section=self.section, target_date=self.entry_date)
            # We only need the latest rule per item
            self.rules_map = {}
            for r in rules:
                if r.item_id not in self.rules_map:
                    self.rules_map[r.item_id] = r

        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs.update(
            {
                "workers_qs": self.workers_qs,
                "items_qs": self.items_qs,
                "rules_map": self.rules_map,
            }
        )
        return kwargs


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm, formset=BaseProductionEntryFormSet, extra=0, min_num=1, validate_min=True
)
