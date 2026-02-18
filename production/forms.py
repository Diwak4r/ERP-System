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
        workers_qs=None,
        items_qs=None,
        skip_hydration: bool = False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.skip_hydration = skip_hydration
        self.fields["worker"].queryset = workers_qs if workers_qs is not None else Worker.objects.filter(is_active=True)
        self.fields["item"].queryset = items_qs if items_qs is not None else Item.objects.filter(is_active=True)
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
        rule = (
            TargetRule.objects.for_section_item_date(section=self.section, item=self.cleaned_data["item"], target_date=self.entry_date)
            .first()
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
        if not self.skip_hydration:
            self._hydrate_targets()
        return cleaned


class BaseProductionEntryFormSet(forms.BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        section = self.form_kwargs.get("section")
        entry_date = self.form_kwargs.get("entry_date")
        if not section or not entry_date:
            return

        items = [f.cleaned_data.get("item") for f in self.forms if f.cleaned_data.get("item")]
        if not items:
            return

        from django.db.models import Q

        rules_qs = (
            TargetRule.objects.filter(section=section, item__in=items, start_date__lte=entry_date)
            .filter(Q(end_date__gte=entry_date) | Q(end_date__isnull=True))
            .order_by("-start_date")
        )

        rules_map = {}
        for rule in rules_qs:
            if rule.item_id not in rules_map:
                rules_map[rule.item_id] = rule

        for form in self.forms:
            item = form.cleaned_data.get("item")
            if not item:
                continue
            rule = rules_map.get(item.id)
            if rule:
                form.cleaned_data["target_qty"] = rule.target_qty
                form.cleaned_data["shift_hours"] = rule.shift_hours
            else:
                form.cleaned_data["target_qty"] = form.cleaned_data.get("target_qty") or 0
                form.cleaned_data["shift_hours"] = form.cleaned_data.get("shift_hours") or 0


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm, formset=BaseProductionEntryFormSet, extra=0, min_num=1, validate_min=True
)
