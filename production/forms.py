from __future__ import annotations

from datetime import date
from typing import Optional

from django import forms

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class BaseProductionEntryFormSet(forms.BaseFormSet):
    def __init__(self, *args, **kwargs):
        self.form_kwargs = kwargs.get("form_kwargs", {})
        self.section = self.form_kwargs.get("section")
        self.entry_date = self.form_kwargs.get("entry_date")
        self.target_rules_cache = {}
        self.worker_qs = Worker.objects.filter(is_active=True)
        self.item_qs = Item.objects.filter(is_active=True)

        if self.section and self.entry_date:
            # Bulk fetch target rules for the section and date
            rules = TargetRule.objects.for_section_item_date(
                section=self.section, target_date=self.entry_date
            )
            # Use the latest rule (first in -start_date order) for each item
            for rule in rules:
                if rule.item_id not in self.target_rules_cache:
                    self.target_rules_cache[rule.item_id] = rule

            # Evaluate choices once to share across all forms
            self.worker_choices = [(w.pk, str(w)) for w in self.worker_qs]
            self.item_choices = [(i.pk, str(i)) for i in self.item_qs]

        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs.update({
            "target_rules_cache": self.target_rules_cache,
            "worker_choices": getattr(self, "worker_choices", None),
            "item_choices": getattr(self, "item_choices", None),
        })
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
        self.target_rules_cache = target_rules_cache or {}

        # Set queryset to ensure validation still works
        self.fields["worker"].queryset = Worker.objects.filter(is_active=True)
        self.fields["item"].queryset = Item.objects.filter(is_active=True)

        # Use pre-evaluated choices to avoid database queries during rendering
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
        item = self.cleaned_data.get("item")
        if not self.section or not self.entry_date or not item:
            return

        # Try to use the cache first to avoid a database query
        rule = self.target_rules_cache.get(item.id)
        if not rule:
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
