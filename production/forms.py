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
        target_rules_cache: dict[int, TargetRule] | None = None,
        worker_choices: list[Worker] | None = None,
        item_choices: list[Item] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.target_rules_cache = target_rules_cache

        if worker_choices is not None:
            self.fields["worker"].queryset = Worker.objects.filter(is_active=True)
            self.fields["worker"].choices = [(w.pk, str(w)) for w in worker_choices]
        else:
            self.fields["worker"].queryset = Worker.objects.filter(is_active=True)

        if item_choices is not None:
            self.fields["item"].queryset = Item.objects.filter(is_active=True)
            self.fields["item"].choices = [(i.pk, str(i)) for i in item_choices]
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
            rule = self.target_rules_cache.get(item.pk)
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
        self._target_rules_cache = {}
        self._worker_choices = None
        self._item_choices = None

        if self.section and self.entry_date:
            # Bulk fetch target rules for the section and date
            rules = TargetRule.objects.for_section_item_date(
                section=self.section, target_date=self.entry_date
            )
            # Cache by item_id. Since it's ordered by -start_date, the first one seen is the most relevant.
            for rule in rules:
                if rule.item_id not in self._target_rules_cache:
                    self._target_rules_cache[rule.item_id] = rule

        # Pre-evaluate choices for workers and items to avoid N queries during form initialization/validation
        self._worker_choices = list(Worker.objects.filter(is_active=True))
        self._item_choices = list(Item.objects.filter(is_active=True))

        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs.update({
            "target_rules_cache": self._target_rules_cache,
            "worker_choices": self._worker_choices,
            "item_choices": self._item_choices,
        })
        return kwargs


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm,
    formset=BaseProductionEntryFormSet,
    extra=0,
    min_num=1,
    validate_min=True,
)
