from __future__ import annotations

from datetime import date
from typing import Any

from django import forms
from django.db import models

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class ProductionEntryForm(forms.ModelForm):
    def __init__(
        self,
        *args,
        section: Section | None = None,
        entry_date: date | None = None,
        worker_choices: list[tuple[Any, str]] | None = None,
        item_choices: list[tuple[Any, str]] | None = None,
        target_rules_cache: dict[int, TargetRule] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.target_rules_cache = target_rules_cache

        # Set up querysets (still needed for validation)
        self.fields["worker"].queryset = Worker.objects.filter(is_active=True)
        self.fields["item"].queryset = Item.objects.filter(is_active=True)

        # Optimization: use pre-evaluated choices if provided
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

        rule = None
        if self.target_rules_cache is not None:
            # Use pre-fetched cache (O(1) lookup)
            rule = self.target_rules_cache.get(item.id)
        else:
            # Fallback to DB query
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
        super().__init__(*args, **kwargs)
        self.worker_choices = None
        self.item_choices = None
        self.target_rules_cache = None

        section = self.form_kwargs.get("section")
        entry_date = self.form_kwargs.get("entry_date")

        if section and entry_date:
            # Pre-evaluate choices for all forms in the set
            # This avoids N+1 queries when rendering the forms
            self.worker_choices = [
                (w.id, str(w)) for w in Worker.objects.filter(is_active=True)
            ]
            self.item_choices = [
                (i.id, str(i)) for i in Item.objects.filter(is_active=True)
            ]

            # Bulk fetch target rules for the entire section on the entry date
            # We filter by section and date, then group by item in a dict
            rules = TargetRule.objects.filter(
                section=section,
                start_date__lte=entry_date,
            ).filter(
                models.Q(end_date__gte=entry_date) | models.Q(end_date__isnull=True)
            ).order_by("-start_date")

            self.target_rules_cache = {}
            for rule in rules:
                if rule.item_id not in self.target_rules_cache:
                    # Since we ordered by -start_date, the first one encountered is the most relevant
                    self.target_rules_cache[rule.item_id] = rule

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs.update({
            "worker_choices": self.worker_choices,
            "item_choices": self.item_choices,
            "target_rules_cache": self.target_rules_cache,
        })
        return kwargs


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm,
    formset=BaseProductionEntryFormSet,
    extra=0,
    min_num=1,
    validate_min=True,
)
