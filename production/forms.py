from __future__ import annotations

from datetime import date
from typing import Optional

from django import forms
from django.db import models

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class BaseProductionEntryFormSet(forms.BaseFormSet):
    def __init__(self, *args, **kwargs):
        self.section = kwargs.get("form_kwargs", {}).get("section")
        self.entry_date = kwargs.get("form_kwargs", {}).get("entry_date")
        super().__init__(*args, **kwargs)

        # Pre-fetch Workers and Items
        # list() evaluates the queryset once
        self.workers_qs = Worker.objects.filter(is_active=True)
        self.workers_list = list(self.workers_qs)
        self.worker_choices = [(w.id, str(w)) for w in self.workers_list]

        self.items_qs = Item.objects.filter(is_active=True)
        self.items_list = list(self.items_qs)
        self.item_choices = [(i.id, str(i)) for i in self.items_list]

        # Pre-fetch TargetRules for the section and date
        self.target_rules_cache = {}
        if self.section and self.entry_date:
            # list() ensures all rules are fetched in a single query
            # reversed() then works on the list in memory
            rules = list(TargetRule.objects.for_section_item_date(section=self.section, target_date=self.entry_date))
            # Use the most recent rule for each item (ordered by -start_date, so we process oldest to newest)
            for rule in reversed(rules):
                self.target_rules_cache[rule.item_id] = rule

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs.update(
            {
                "worker_choices": self.worker_choices,
                "item_choices": self.item_choices,
                "workers_qs": self.workers_qs,
                "items_qs": self.items_qs,
                "target_rules_cache": self.target_rules_cache,
            }
        )
        return kwargs


class ProductionEntryForm(forms.ModelForm):
    def __init__(
        self,
        *args,
        section: Optional[Section] = None,
        entry_date: Optional[date] = None,
        worker_choices: Optional[list] = None,
        item_choices: Optional[list] = None,
        workers_qs: Optional[models.QuerySet] = None,
        items_qs: Optional[models.QuerySet] = None,
        target_rules_cache: Optional[dict] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.target_rules_cache = target_rules_cache

        # Optimization: use pre-evaluated querysets to avoid N+1 queries during validation
        if workers_qs is not None:
            self.fields["worker"].queryset = workers_qs
        else:
            self.fields["worker"].queryset = Worker.objects.filter(is_active=True)

        if items_qs is not None:
            self.fields["item"].queryset = items_qs
        else:
            self.fields["item"].queryset = Item.objects.filter(is_active=True)

        # Optimization: use pre-evaluated choices to avoid N+1 queries during rendering
        if worker_choices is not None:
            self.fields["worker"].choices = worker_choices
        if item_choices is not None:
            self.fields["item"].choices = item_choices

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


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm, formset=BaseProductionEntryFormSet, extra=0, min_num=1, validate_min=True
)
