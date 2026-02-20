from __future__ import annotations

from datetime import date
from typing import Optional

from django import forms
from django.db import models

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class ProductionEntryForm(forms.ModelForm):
    def __init__(
        self,
        *args,
        section: Optional[Section] = None,
        entry_date: Optional[date] = None,
        rules_cache: Optional[dict] = None,
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
        # ⚡ Bolt: Use prefetched cache from FormSet to avoid N+1 queries
        if self.rules_cache is not None:
            rule = self.rules_cache.get(item.id)
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
    """
    ⚡ Bolt: Custom FormSet to prefetch TargetRules and avoid N+1 queries during validation.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rules_cache = None

    def _prefetch_rules(self) -> dict:
        section = self.form_kwargs.get("section")
        entry_date = self.form_kwargs.get("entry_date")
        if not (section and entry_date and self.is_bound):
            return {}

        # Collect all item IDs from the POST data to fetch rules in bulk
        item_ids = []
        for i in range(self.total_form_count()):
            item_id = self.data.get(f"{self.prefix}-{i}-item")
            if item_id:
                try:
                    item_ids.append(int(item_id))
                except (ValueError, TypeError):
                    continue

        if not item_ids:
            return {}

        # Fetch all rules for these items on the given date
        rules = (
            TargetRule.objects.filter(section=section, item_id__in=item_ids, start_date__lte=entry_date)
            .filter(models.Q(end_date__gte=entry_date) | models.Q(end_date__isnull=True))
            .order_by("item_id", "-start_date")
        )

        # Map item_id to the most recent rule (first one after ordering by -start_date)
        cache = {}
        for rule in rules:
            if rule.item_id not in cache:
                cache[rule.item_id] = rule
        return cache

    def get_form_kwargs(self, index: int) -> dict:
        kwargs = super().get_form_kwargs(index)
        if self._rules_cache is None:
            self._rules_cache = self._prefetch_rules()
        kwargs["rules_cache"] = self._rules_cache
        return kwargs


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm, formset=BaseProductionEntryFormSet, extra=0, min_num=1, validate_min=True
)
