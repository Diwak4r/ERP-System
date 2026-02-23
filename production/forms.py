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
        worker_queryset: Optional[forms.QuerySet] = None,
        item_queryset: Optional[forms.QuerySet] = None,
        target_rules_cache: Optional[dict[int, TargetRule]] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.section = section
        self.entry_date = entry_date
        self.target_rules_cache = target_rules_cache

        # Use shared querysets if provided to avoid redundant DB hits during validation/rendering
        if worker_queryset is not None:
            self.fields["worker"].queryset = worker_queryset
        else:
            self.fields["worker"].queryset = Worker.objects.filter(is_active=True)

        if item_queryset is not None:
            self.fields["item"].queryset = item_queryset
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
        if not self.section or not self.entry_date or not self.cleaned_data.get("item"):
            return

        item = self.cleaned_data["item"]
        rule = None

        # Use cache if available (populated by the formset) to avoid N+1 queries
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
    """
    FormSet for ProductionEntry that optimizes performance by pre-fetching
    active workers, items, and applicable target rules in a single query.
    """

    def __init__(self, *args, **kwargs):
        form_kwargs = kwargs.get("form_kwargs", {})
        self.section = form_kwargs.get("section")
        self.entry_date = form_kwargs.get("entry_date")
        super().__init__(*args, **kwargs)
        self._worker_queryset = None
        self._item_queryset = None
        self._target_rules_cache = None

    def get_worker_queryset(self):
        if self._worker_queryset is None:
            self._worker_queryset = Worker.objects.filter(is_active=True)
        return self._worker_queryset

    def get_item_queryset(self):
        if self._item_queryset is None:
            self._item_queryset = Item.objects.filter(is_active=True)
        return self._item_queryset

    def get_target_rules_cache(self) -> dict[int, TargetRule]:
        if self._target_rules_cache is None:
            if not self.section or not self.entry_date:
                return {}

            # Fetch all rules for this section that cover the entry date
            # and take the most recent one (highest start_date) for each item.
            rules = (
                TargetRule.objects.filter(section=self.section)
                .filter(Q(start_date__lte=self.entry_date))
                .filter(Q(end_date__gte=self.entry_date) | Q(end_date__isnull=True))
                .order_by("-start_date")
            )
            cache = {}
            for rule in rules:
                if rule.item_id not in cache:
                    cache[rule.item_id] = rule
            self._target_rules_cache = cache
        return self._target_rules_cache

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs.update(
            {
                "worker_queryset": self.get_worker_queryset(),
                "item_queryset": self.get_item_queryset(),
                "target_rules_cache": self.get_target_rules_cache(),
            }
        )
        return kwargs


ProductionEntryFormSet = forms.formset_factory(
    ProductionEntryForm, formset=BaseProductionEntryFormSet, extra=0, min_num=1, validate_min=True
)
