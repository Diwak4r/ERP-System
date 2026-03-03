from __future__ import annotations

from datetime import date
from typing import Optional

from django import forms
from django.db import models

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class BaseProductionEntryFormSet(forms.BaseFormSet):
    """
    Optimizes performance by bulk-fetching validation data (workers, items, target rules)
    once for all forms in the formset.
    """

    def __init__(self, *args, **kwargs):
        self.section = kwargs.get("form_kwargs", {}).get("section")
        self.entry_date = kwargs.get("form_kwargs", {}).get("entry_date")
        super().__init__(*args, **kwargs)

        # Pre-fetch workers and items once for all forms
        self.worker_qs = Worker.objects.filter(is_active=True)
        self.item_qs = Item.objects.filter(is_active=True)

        # Pre-fetch all target rules for the section and date in one query
        self.rules_cache = {}
        if self.section and self.entry_date:
            rules = TargetRule.objects.for_section_item_date(
                section=self.section, target_date=self.entry_date
            )
            # Use item_id as key, picking the latest rule per item (order_by handles this)
            for rule in rules:
                if rule.item_id not in self.rules_cache:
                    self.rules_cache[rule.item_id] = rule

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs.update(
            {
                "rules_cache": self.rules_cache,
                "worker_qs": self.worker_qs,
                "item_qs": self.item_qs,
            }
        )
        return kwargs


class ProductionEntryForm(forms.ModelForm):
    def __init__(
        self,
        *args,
        section: Optional[Section] = None,
        entry_date: Optional[date] = None,
        rules_cache: Optional[dict[int, TargetRule]] = None,
        worker_qs: Optional[models.QuerySet] = None,
        item_qs: Optional[models.QuerySet] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.rules_cache = rules_cache
        self.fields["worker"].queryset = worker_qs if worker_qs is not None else Worker.objects.filter(is_active=True)
        self.fields["item"].queryset = item_qs if item_qs is not None else Item.objects.filter(is_active=True)
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

        # Optimization: use bulk-fetched rules cache if available
        if self.rules_cache is not None:
            rule = self.rules_cache.get(item.id)
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


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm,
    formset=BaseProductionEntryFormSet,
    extra=0,
    min_num=1,
    validate_min=True,
)
