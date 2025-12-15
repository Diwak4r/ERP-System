from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models

User = get_user_model()


class Section(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    supervisors = models.ManyToManyField(User, related_name="sections", blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return self.name


class Worker(models.Model):
    name = models.CharField(max_length=255)
    employee_code = models.CharField(max_length=50, unique=True)
    is_daily_wage = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return f"{self.name} ({self.employee_code})"


class Item(models.Model):
    UNIT_KG = "KG"
    UNIT_PCS = "PCS"
    UNIT_OTHER = "OTHER"
    UNIT_CHOICES = [
        (UNIT_KG, "Kg"),
        (UNIT_PCS, "Pieces"),
        (UNIT_OTHER, "Other"),
    ]

    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, unique=True)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default=UNIT_PCS)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return f"{self.name} ({self.sku})"


class TargetRuleQuerySet(models.QuerySet):
    def for_section_item_date(self, *, section: Section, item: Item, target_date: date):
        return self.filter(
            section=section,
            item=item,
            start_date__lte=target_date,
        ).filter(models.Q(end_date__gte=target_date) | models.Q(end_date__isnull=True)).order_by(
            "-start_date"
        )


class TargetRule(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    target_qty = models.DecimalField(max_digits=12, decimal_places=2)
    shift_hours = models.DecimalField(max_digits=5, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    objects = TargetRuleQuerySet.as_manager()

    class Meta:
        unique_together = ("section", "item", "start_date", "end_date")
        ordering = ["section__name", "item__name", "-start_date"]

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return f"{self.section} - {self.item} ({self.start_date} to {self.end_date or 'open'})"

    def clean(self) -> None:
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError("End date cannot be earlier than start date")


class ProductionEntry(models.Model):
    entry_date = models.DateField()
    section = models.ForeignKey(Section, on_delete=models.PROTECT)
    worker = models.ForeignKey(Worker, on_delete=models.PROTECT)
    item = models.ForeignKey(Item, on_delete=models.PROTECT)

    target_qty = models.DecimalField(max_digits=12, decimal_places=2)
    actual_qty = models.DecimalField(max_digits=12, decimal_places=2)
    shift_hours = models.DecimalField(max_digits=5, decimal_places=2)
    overtime_hours = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))
    target_met = models.BooleanField(default=False)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="production_entries")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-entry_date", "section__name", "worker__name"]
        indexes = [
            models.Index(fields=["entry_date", "section", "item"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return f"{self.entry_date} - {self.section} - {self.worker}"

    @staticmethod
    def compute_overtime(actual_qty: Decimal, target_qty: Decimal, shift_hours: Decimal) -> Decimal:
        if target_qty <= 0 or shift_hours <= 0:
            return Decimal("0")
        ratio = (actual_qty / target_qty) - Decimal("1")
        if ratio <= 0:
            return Decimal("0")
        return (ratio * shift_hours).quantize(Decimal("0.01"))

    def clean(self) -> None:
        if self.entry_date and self.entry_date < date.today():
            # Hook for future immutability rules; raising validation for new entries could block.
            return

    def set_outcomes(self) -> None:
        self.target_met = self.actual_qty >= self.target_qty if self.target_qty is not None else False
        self.overtime_hours = self.compute_overtime(self.actual_qty, self.target_qty, self.shift_hours)
