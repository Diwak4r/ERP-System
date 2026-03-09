from __future__ import annotations

from datetime import date
from typing import Optional

from django import forms
from django.db import models

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class BaseProductionEntryFormSet(forms.BaseFormSet):
    def __init__(self, *args, **kwargs):
        # Extract section and entry_date from form_kwargs if available
        form_kwargs = kwargs.get("form_kwargs", {})
        self.section = form_kwargs.get("section")
        self.entry_date = form_kwargs.get("entry_date")

        self.target_rules_cache = {}
        if self.section and self.entry_date:
            rules = TargetRule.objects.for_section_item_date(section=self.section, target_date=self.entry_date)
            # Map item_id -> TargetRule. Since rules are ordered by -start_date, the first one seen for each item is the most relevant.
            for rule in rules:
                if rule.item_id not in self.target_rules_cache:
                    self.target_rules_cache[rule.item_id] = rule

        # Pre-fetch workers and items as static choices once for all forms
        self.worker_choices = [(w.id, str(w)) for w in Worker.objects.filter(is_active=True)]
        self.item_choices = [(i.id, str(i)) for i in Item.objects.filter(is_active=True)]

        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs.update(
            {
                "target_rules_cache": self.target_rules_cache,
                "worker_choices": self.worker_choices,
                "item_choices": self.item_choices,
            }
        )
        return kwargs


class ProductionEntryForm(forms.ModelForm):
    def __init__(
        self,
        *args,
        section: Optional[Section] = None,
        entry_date: Optional[date] = None,
        target_rules_cache: Optional[dict] = None,
        worker_choices: Optional[list] = None,
        item_choices: Optional[list] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.target_rules_cache = target_rules_cache

        active_workers = Worker.objects.filter(is_active=True)
        active_items = Item.objects.filter(is_active=True)

        if worker_choices is not None:
            self.fields["worker"].choices = worker_choices
            self.fields["worker"].queryset = active_workers
        else:
            self.fields["worker"].queryset = active_workers

        if item_choices is not None:
            self.fields["item"].choices = item_choices
            self.fields["item"].queryset = active_items
        else:
            self.fields["item"].queryset = active_items


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
