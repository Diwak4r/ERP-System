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
        section: Optional[Section] = None,
        entry_date: Optional[date] = None,
        worker_qs=None,
        item_qs=None,
        target_rule_cache=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.target_rule_cache = target_rule_cache

        # Optimization: use pre-fetched querysets if provided
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

        rule = None
        if self.target_rule_cache is not None:
            # Optimization: Use pre-fetched cache
            rule = self.target_rule_cache.get(item.id)
        else:
            rule = (
                TargetRule.objects.for_section_item_date(
                    section=self.section, item=item, target_date=self.entry_date
                ).first()
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


class BaseProductionEntryFormSet(forms.BaseFormSet):
    def __init__(self, *args, **kwargs):
        self.form_kwargs = kwargs.get("form_kwargs", {})
        self.section = self.form_kwargs.get("section")
        self.entry_date = self.form_kwargs.get("entry_date")

        # Pre-fetch data once for all forms in the formset
        self.worker_qs = Worker.objects.filter(is_active=True)
        self.item_qs = Item.objects.filter(is_active=True)

        self.target_rule_cache = {}
        if self.section and self.entry_date:
            # Pre-fetch all relevant rules for the section and date once
            rules = (
                TargetRule.objects.filter(
                    section=self.section,
                    start_date__lte=self.entry_date,
                )
                .filter(models.Q(end_date__gte=self.entry_date) | models.Q(end_date__isnull=True))
                .order_by("item", "-start_date")
            )

            # Simple cache: only take the most recent rule per item
            for rule in rules:
                if rule.item_id not in self.target_rule_cache:
                    self.target_rule_cache[rule.item_id] = rule

        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs.update({
            "worker_qs": self.worker_qs,
            "item_qs": self.item_qs,
            "target_rule_cache": self.target_rule_cache,
        })
        return kwargs


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm,
    formset=BaseProductionEntryFormSet,
    extra=0,
    min_num=1,
    validate_min=True,
)
