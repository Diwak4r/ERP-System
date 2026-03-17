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
        worker_choices: list | None = None,
        item_choices: list | None = None,
        rules_cache: dict[int, TargetRule] | None = None,
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
        if not self.section or not self.entry_date or not self.cleaned_data.get("item"):
            return

        item = self.cleaned_data["item"]
        rule = None
        if self.rules_cache is not None:
            rule = self.rules_cache.get(item.id)
        else:
            rule = TargetRule.objects.for_section_item_date(section=self.section, item=item, target_date=self.entry_date).first()

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
        self.section = self.form_kwargs.get("section")
        self.entry_date = self.form_kwargs.get("entry_date")

        # Cache worker and item choices to avoid N+1 queries during rendering
        self.worker_choices = [("", "---------")] + [(w.id, str(w)) for w in Worker.objects.filter(is_active=True)]
        self.item_choices = [("", "---------")] + [(i.id, str(i)) for i in Item.objects.filter(is_active=True)]

        # Cache target rules for the section and date
        self.rules_cache = {}
        if self.section and self.entry_date:
            rules = TargetRule.objects.for_section_item_date(section=self.section, target_date=self.entry_date)
            for rule in rules:
                if rule.item_id not in self.rules_cache:
                    self.rules_cache[rule.item_id] = rule

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs.update(
            {
                "worker_choices": self.worker_choices,
                "item_choices": self.item_choices,
                "rules_cache": self.rules_cache,
            }
        )
        return kwargs


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm, formset=BaseProductionEntryFormSet, extra=0, min_num=1, validate_min=True
)
