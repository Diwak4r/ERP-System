from __future__ import annotations

from datetime import date
from typing import Optional

from django import forms
from django.db.models import Q
from django.forms import BaseFormSet

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class BaseProductionEntryFormSet(BaseFormSet):
    def __init__(self, *args, **kwargs):
        self.section = kwargs.get("form_kwargs", {}).get("section")
        self.entry_date = kwargs.get("form_kwargs", {}).get("entry_date")
        self._rules_cache = None
        super().__init__(*args, **kwargs)

    @property
    def rules_cache(self):
        if self._rules_cache is None and self.section and self.entry_date:
            # Pre-fetch all rules for this section and date
            rules = TargetRule.objects.filter(
                section=self.section,
                start_date__lte=self.entry_date,
            ).filter(
                Q(end_date__gte=self.entry_date) | Q(end_date__isnull=True)
            ).order_by("-start_date")

            # Map item_id to the most recent rule
            self._rules_cache = {}
            for rule in rules:
                if rule.item_id not in self._rules_cache:
                    self._rules_cache[rule.item_id] = rule
        return self._rules_cache or {}

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["rules_cache"] = self.rules_cache
        return kwargs


class ProductionEntryForm(forms.ModelForm):
    def __init__(self, *args, section: Optional[Section] = None, entry_date: Optional[date] = None, rules_cache=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.rules_cache = rules_cache
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

        item = self.cleaned_data["item"]
        rule = None
        if self.rules_cache is not None:
            rule = self.rules_cache.get(item.id)
        else:
            rule = (
                TargetRule.objects.for_section_item_date(section=self.section, item=item, target_date=self.entry_date)
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


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm,
    formset=BaseProductionEntryFormSet,
    extra=0,
    min_num=1,
    validate_min=True,
)
