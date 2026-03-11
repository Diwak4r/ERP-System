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
        targets_cache: Optional[dict[int, TargetRule]] = None,
        workers_cache: Optional[dict[int, Worker]] = None,
        items_cache: Optional[dict[int, Item]] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.targets_cache = targets_cache
        self.workers_cache = workers_cache
        self.items_cache = items_cache

        if workers_cache is not None:
            # Use ChoiceField to avoid ModelChoiceField validation queries
            self.fields["worker"] = forms.ChoiceField(
                choices=[(w.pk, str(w)) for w in workers_cache.values()],
            )
        else:
            self.fields["worker"].queryset = Worker.objects.filter(is_active=True)

        if items_cache is not None:
            # Use ChoiceField to avoid ModelChoiceField validation queries
            self.fields["item"] = forms.ChoiceField(
                choices=[(i.pk, str(i)) for i in items_cache.values()],
            )
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
        if self.targets_cache is not None:
            rule = self.targets_cache.get(item.id)
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

    def clean_worker(self):
        worker = self.cleaned_data.get("worker")
        if self.workers_cache is not None:
            try:
                return self.workers_cache[int(worker)]
            except (KeyError, ValueError, TypeError):
                raise forms.ValidationError("Invalid worker selection")
        return worker

    def clean_item(self):
        item = self.cleaned_data.get("item")
        if self.items_cache is not None:
            try:
                return self.items_cache[int(item)]
            except (KeyError, ValueError, TypeError):
                raise forms.ValidationError("Invalid item selection")
        return item

    def clean(self):
        cleaned = super().clean()
        self._hydrate_targets()
        return cleaned


class BaseProductionEntryFormSet(forms.BaseFormSet):
    def __init__(self, *args, **kwargs):
        self.section = kwargs.get("form_kwargs", {}).get("section")
        self.entry_date = kwargs.get("form_kwargs", {}).get("entry_date")
        self._targets_cache = None
        self._workers_cache = None
        self._items_cache = None
        super().__init__(*args, **kwargs)

    @property
    def targets_cache(self) -> dict[int, TargetRule]:
        if self._targets_cache is None and self.section and self.entry_date:
            rules = TargetRule.objects.for_section_item_date(section=self.section, target_date=self.entry_date)
            # Use a dict to store the most recent rule for each item
            self._targets_cache = {}
            for rule in rules:
                if rule.item_id not in self._targets_cache:
                    self._targets_cache[rule.item_id] = rule
        return self._targets_cache or {}

    @property
    def workers_cache(self) -> dict[int, Worker]:
        if self._workers_cache is None:
            qs = list(Worker.objects.filter(is_active=True))
            self._workers_cache = {w.pk: w for w in qs}
        return self._workers_cache

    @property
    def items_cache(self) -> dict[int, Item]:
        if self._items_cache is None:
            qs = list(Item.objects.filter(is_active=True))
            self._items_cache = {i.pk: i for i in qs}
        return self._items_cache

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["targets_cache"] = self.targets_cache
        kwargs["workers_cache"] = self.workers_cache
        kwargs["items_cache"] = self.items_cache
        return kwargs


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm,
    formset=BaseProductionEntryFormSet,
    extra=0,
    min_num=1,
    validate_min=True,
)
