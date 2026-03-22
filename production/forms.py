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
        worker_choices: list[tuple[int, str]] | None = None,
        item_choices: list[tuple[int, str]] | None = None,
        target_rules_cache: dict[int, TargetRule] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.target_rules_cache = target_rules_cache

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
    def __init__(self, *args, **kwargs):
        form_kwargs = kwargs.get("form_kwargs", {})
        section = form_kwargs.get("section")
        entry_date = form_kwargs.get("entry_date")

        if section and entry_date:
            # Pre-fetch choices
            worker_choices = [(w.id, str(w)) for w in Worker.objects.filter(is_active=True)]
            item_choices = [(i.id, str(i)) for i in Item.objects.filter(is_active=True)]

            # Pre-fetch TargetRules for the entire section and date
            rules = TargetRule.objects.for_section_item_date(section=section, target_date=entry_date)
            # Map item_id -> latest rule (due to -start_date ordering)
            target_rules_cache = {}
            for r in rules:
                if r.item_id not in target_rules_cache:
                    target_rules_cache[r.item_id] = r

            self.shared_prefetched_data = {
                "worker_choices": worker_choices,
                "item_choices": item_choices,
                "target_rules_cache": target_rules_cache,
            }
        else:
            self.shared_prefetched_data = {}

        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs.update(self.shared_prefetched_data)
        return kwargs


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm, formset=BaseProductionEntryFormSet, extra=0, min_num=1, validate_min=True
)
