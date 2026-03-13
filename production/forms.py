from __future__ import annotations

from datetime import date
from typing import Any, Optional

from django import forms

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class ProductionEntryForm(forms.ModelForm):
    def __init__(
        self,
        *args,
        section: Optional[Section] = None,
        entry_date: Optional[date] = None,
        worker_choices: Optional[list[tuple[Any, str]]] = None,
        item_choices: Optional[list[tuple[Any, str]]] = None,
        target_rules_cache: Optional[dict[int, TargetRule]] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.target_rules_cache = target_rules_cache

        # Optimization: Use pre-evaluated choices to avoid redundant queries per form
        if worker_choices is not None:
            self.fields["worker"].choices = worker_choices
        else:
            self.fields["worker"].queryset = Worker.objects.filter(is_active=True)

        if item_choices is not None:
            self.fields["item"].choices = item_choices
        else:
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
        item = self.cleaned_data.get("item")
        if not self.section or not self.entry_date or not item:
            return

        rule = None
        if self.target_rules_cache is not None:
            rule = self.target_rules_cache.get(item.id)
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
        form_kwargs = kwargs.get("form_kwargs", {})
        self.section = form_kwargs.get("section")
        self.entry_date = form_kwargs.get("entry_date")

        # Optimization: Pre-evaluate choices once for all forms in the set
        # This reduces queries from O(N) to O(1) for choice field initialization
        workers = Worker.objects.filter(is_active=True)
        self.worker_choices = [(w.pk, str(w)) for w in workers]

        items = Item.objects.filter(is_active=True)
        self.item_choices = [(i.pk, str(i)) for i in items]

        self.target_rules_cache: dict[int, TargetRule] = {}

        if self.section and self.entry_date:
            # Optimization: Fetch all relevant rules for the section in one query
            rules = TargetRule.objects.for_section_item_date(
                section=self.section, target_date=self.entry_date
            )
            # Since rules are ordered by -start_date, the first one we see for each item is the most relevant
            for rule in rules:
                if rule.item_id not in self.target_rules_cache:
                    self.target_rules_cache[rule.item_id] = rule

        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index: int | None) -> dict[str, Any]:
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
