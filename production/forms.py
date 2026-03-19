from __future__ import annotations

from datetime import date
from typing import Optional

from django import forms

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class BaseProductionEntryFormSet(forms.BaseFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-fetch data to avoid N+1 queries in forms
        section = self.form_kwargs.get("section")
        entry_date = self.form_kwargs.get("entry_date")

        self.worker_choices = list(Worker.objects.filter(is_active=True).values_list("id", "name"))
        self.item_choices = list(Item.objects.filter(is_active=True).values_list("id", "name"))
        self.rules_cache = {}

        if section and entry_date:
            rules = TargetRule.objects.for_section_item_date(section=section, target_date=entry_date)
            # Use a dict for O(1) lookups in forms; only the most recent rule per item is needed
            for rule in rules:
                if rule.item_id not in self.rules_cache:
                    self.rules_cache[rule.item_id] = rule

    def get_form_kwargs(self, index: int | None):
        kwargs = super().get_form_kwargs(index)
        kwargs.update(
            {
                "worker_choices": self.worker_choices,
                "item_choices": self.item_choices,
                "rules_cache": self.rules_cache,
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
        rules_cache: Optional[dict] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.rules_cache = rules_cache

        self.fields["worker"].queryset = Worker.objects.filter(is_active=True)
        self.fields["item"].queryset = Item.objects.filter(is_active=True)

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
        if self.rules_cache is not None:
            rule = self.rules_cache.get(item.id if isinstance(item, Item) else item)
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


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm, formset=BaseProductionEntryFormSet, extra=0, min_num=1, validate_min=True
)
