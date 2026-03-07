from __future__ import annotations

from datetime import date
from typing import Optional

from django import forms

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class ProductionEntryForm(forms.ModelForm):
    def __init__(
        self,
        *args,
        section: Optional[Section] = None,
        entry_date: Optional[date] = None,
        target_rule_map: Optional[dict[int, TargetRule]] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.target_rule_map = target_rule_map
        self.fields["worker"].queryset = Worker.objects.filter(is_active=True)
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
        if not self.section or not self.entry_date or not self.cleaned_data.get("item"):
            return

        item = self.cleaned_data["item"]
        if self.target_rule_map is not None:
            rule = self.target_rule_map.get(item.id)
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
    def get_form_kwargs(self, index: int) -> dict:
        kwargs = super().get_form_kwargs(index)
        if self.is_bound:
            # Pre-fetch target rules for the whole section on this date to avoid N+1 queries during validation
            section = kwargs.get("section")
            entry_date = kwargs.get("entry_date")
            if section and entry_date:
                if not hasattr(self, "_target_rule_map"):
                    # Execute the query once and cache it on the formset instance
                    rules = TargetRule.objects.for_section_item_date(section=section, target_date=entry_date)
                    # Map item_id to rule. Since for_section_item_date orders by -start_date,
                    # the first rule encountered for each item is the most recent (correct) one.
                    self._target_rule_map = {}
                    for r in rules:
                        if r.item_id not in self._target_rule_map:
                            self._target_rule_map[r.item_id] = r
                kwargs["target_rule_map"] = self._target_rule_map
        return kwargs


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm, formset=BaseProductionEntryFormSet, extra=0, min_num=1, validate_min=True
)
