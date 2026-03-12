from __future__ import annotations

from datetime import date
from typing import Optional

from django import forms
from django.db import models

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class ProductionEntryForm(forms.ModelForm):
    def __init__(
        self,
        *args,
        section: Section | None = None,
        entry_date: date | None = None,
        worker_qs: models.QuerySet[Worker] | None = None,
        item_qs: models.QuerySet[Item] | None = None,
        target_rules_cache: dict[int, TargetRule] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.target_rules_cache = target_rules_cache

        # Optimization: Use pre-fetched querysets if provided to avoid N+1 queries
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
        item = self.cleaned_data.get("item")
        if not self.section or not self.entry_date or not item:
            return

        # Optimization: Use cache if available
        if self.target_rules_cache is not None:
            rule = self.target_rules_cache.get(item.id)
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
    """
    Optimized FormSet that bulk-fetches common data once to avoid N+1 queries in individual forms.
    """

    def __init__(self, *args, **kwargs):
        form_kwargs = kwargs.get("form_kwargs", {})
        self.section = form_kwargs.get("section")
        self.entry_date = form_kwargs.get("entry_date")

        # Pre-fetch data once for all forms in the set
        self.worker_qs = Worker.objects.filter(is_active=True)
        self.item_qs = Item.objects.filter(is_active=True)
        self.target_rules_cache: dict[int, TargetRule] = {}

        if self.section and self.entry_date:
            # Bulk fetch all relevant target rules for this section and date
            rules = TargetRule.objects.for_section_item_date(section=self.section, target_date=self.entry_date)
            # Cache only the latest rule for each item
            for rule in rules:
                if rule.item_id not in self.target_rules_cache:
                    self.target_rules_cache[rule.item_id] = rule

        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index: int | None) -> dict:
        kwargs = super().get_form_kwargs(index)
        kwargs.update(
            {
                "worker_qs": self.worker_qs,
                "item_qs": self.item_qs,
                "target_rules_cache": self.target_rules_cache,
            }
        )
        return kwargs


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm, formset=BaseProductionEntryFormSet, extra=0, min_num=1, validate_min=True
)
