from __future__ import annotations

from datetime import date
from typing import Optional

from django import forms

from .models import Item, ProductionEntry, Section, TargetRule, Worker


class CachedModelChoiceField(forms.ModelChoiceField):
    """
    A ModelChoiceField that uses a provided cache to avoid database lookups during validation.
    """

    def __init__(self, *args, cache=None, **kwargs):
        self.cache = cache
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if self.cache is not None:
            try:
                key = int(value)
                if key in self.cache:
                    return self.cache[key]
            except (ValueError, TypeError):
                pass
        return super().to_python(value)

    def validate(self, value):
        if value is not None and self.cache is not None:
            if value.id not in self.cache:
                raise forms.ValidationError(
                    self.error_messages["invalid_choice"],
                    code="invalid_choice",
                    params={"value": value},
                )
            return
        super().validate(value)


class ProductionEntryForm(forms.ModelForm):
    def __init__(
        self,
        *args,
        section: Optional[Section] = None,
        entry_date: Optional[date] = None,
        workers_cache=None,
        items_cache=None,
        target_rules_cache=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.target_rules_cache = target_rules_cache

        # Optimization: use CachedModelChoiceField to avoid N+1 queries during validation
        self.fields["worker"] = CachedModelChoiceField(
            queryset=Worker.objects.filter(is_active=True),
            cache=workers_cache,
            required=True,
        )
        self.fields["item"] = CachedModelChoiceField(
            queryset=Item.objects.filter(is_active=True),
            cache=items_cache,
            required=True,
        )

        if workers_cache is not None:
            self.fields["worker"].queryset._result_cache = list(workers_cache.values())
            self.fields["worker"].queryset._prefetch_done = True

        if items_cache is not None:
            self.fields["item"].queryset._result_cache = list(items_cache.values())
            self.fields["item"].queryset._prefetch_done = True

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

        if self.target_rules_cache is not None:
            # Optimization: use pre-fetched cache (item.id -> TargetRule)
            rule = self.target_rules_cache.get(item.id)
        else:
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
        # If target_qty and shift_hours were hydrated, we can remove the 'required' error
        if self._errors.get("target_qty") and self.cleaned_data.get("target_qty") is not None:
            del self._errors["target_qty"]
        if self._errors.get("shift_hours") and self.cleaned_data.get("shift_hours") is not None:
            del self._errors["shift_hours"]
        return cleaned


class BaseProductionEntryFormSet(forms.BaseFormSet):
    def __init__(self, *args, **kwargs):
        form_kwargs = kwargs.get("form_kwargs", {})
        self.section = form_kwargs.get("section")
        self.entry_date = form_kwargs.get("entry_date")

        # Pre-fetch data to avoid N+1 queries during form initialization and validation
        self.workers_cache = {w.id: w for w in Worker.objects.filter(is_active=True)}
        self.items_cache = {i.id: i for i in Item.objects.filter(is_active=True)}

        self.target_rules_cache = None
        if self.section and self.entry_date:
            rules = TargetRule.objects.for_section_item_date(section=self.section, target_date=self.entry_date)
            # Map item_id to rule (TargetRuleQuerySet.for_section_item_date returns ordered by -start_date,
            # so we only take the first one for each item)
            self.target_rules_cache = {}
            for r in rules:
                if r.item_id not in self.target_rules_cache:
                    self.target_rules_cache[r.item_id] = r

        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs.update(
            {
                "workers_cache": self.workers_cache,
                "items_cache": self.items_cache,
                "target_rules_cache": self.target_rules_cache,
            }
        )
        return kwargs


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm, formset=BaseProductionEntryFormSet, extra=0, min_num=1, validate_min=True
)
