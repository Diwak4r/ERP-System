from __future__ import annotations

from datetime import date
from typing import Optional

from django import forms

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class ProductionEntryForm(forms.ModelForm):
    def __init__(
        self,
        *args,
        section: Section | None = None,
        entry_date: date | None = None,
        worker_choices: list | None = None,
        item_choices: list | None = None,
        target_rules_cache: dict[int, TargetRule] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.target_rules_cache = target_rules_cache

        # Always set queryset to ensure validation logic remains consistent (only active records)
        # Even if choices are provided for optimized rendering, ModelChoiceField uses queryset for validation
        worker_qs = Worker.objects.filter(is_active=True)
        self.fields["worker"].queryset = worker_qs
        if worker_choices is not None:
            self.fields["worker"].choices = worker_choices

        item_qs = Item.objects.filter(is_active=True)
        self.fields["item"].queryset = item_qs
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
            rule = TargetRule.objects.for_section_item_date(section=self.section, item=item, target_date=self.entry_date).first()

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
        self.worker_choices = None
        self.item_choices = None
        self.target_rules_cache = None

        if self.section and self.entry_date:
            # Pre-fetch workers and items to avoid N+1 queries in choice field rendering and validation
            # Evaluation of querysets into choices avoids redundant queries during form initialization
            self.worker_choices = [(w.id, str(w)) for w in Worker.objects.filter(is_active=True)]
            self.item_choices = [(i.id, str(i)) for i in Item.objects.filter(is_active=True)]

            # Pre-fetch target rules for the entire section and date range
            rules = TargetRule.objects.for_section_item_date(section=self.section, item=None, target_date=self.entry_date)
            # Create a cache mapping item_id to the most recent/applicable TargetRule
            self.target_rules_cache = {}
            for rule in rules:
                if rule.item_id not in self.target_rules_cache:
                    self.target_rules_cache[rule.item_id] = rule

        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs.update(
            {
                "worker_choices": self.worker_choices,
                "item_choices": self.item_choices,
                "target_rules_cache": self.target_rules_cache,
            }
        )
        return kwargs


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm, formset=BaseProductionEntryFormSet, extra=0, min_num=1, validate_min=True
)
