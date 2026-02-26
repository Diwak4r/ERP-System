from __future__ import annotations

from datetime import date
from typing import Optional

from django import forms
from django.db.models import Q

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class ProductionEntryForm(forms.ModelForm):
    def __init__(
        self,
        *args,
        section: Optional[Section] = None,
        entry_date: Optional[date] = None,
        rules_cache: Optional[dict[int, TargetRule]] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.rules_cache = rules_cache
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
        rule = None

        if self.rules_cache is not None:
            # Use pre-fetched rules from FormSet to avoid N+1 queries
            rule = self.rules_cache.get(item.id)
        else:
            # Fallback to individual query if no cache provided
            rule = (
                TargetRule.objects.for_section_item_date(section=self.section, item=item, target_date=self.entry_date).first()
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
    """
    Optimized FormSet that pre-fetches TargetRules to avoid N+1 queries in forms.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        form_kwargs = kwargs.get("form_kwargs", {})
        self.section = form_kwargs.get("section")
        self.entry_date = form_kwargs.get("entry_date")
        self._rules_cache = None

        if self.section and self.entry_date:
            # Pre-fetch all rules for this section and date in one query
            rules = (
                TargetRule.objects.filter(section=self.section, start_date__lte=self.entry_date)
                .filter(Q(end_date__gte=self.entry_date) | Q(end_date__isnull=True))
                .order_by("item_id", "-start_date")
            )

            # Group by item_id, keeping only the most recent rule per item
            self._rules_cache = {}
            for rule in rules:
                if rule.item_id not in self._rules_cache:
                    self._rules_cache[rule.item_id] = rule

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["rules_cache"] = self._rules_cache
        return kwargs


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm, formset=BaseProductionEntryFormSet, extra=0, min_num=1, validate_min=True
)
