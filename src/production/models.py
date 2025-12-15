from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone


class Section(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - simple repr
        return f"{self.name} ({self.code})"


class Worker(models.Model):
    name = models.CharField(max_length=100)
    employee_code = models.CharField(max_length=30, unique=True)
    is_daily_wage = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover
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

    name = models.CharField(max_length=100)
    sku = models.CharField(max_length=50, unique=True)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default=UNIT_PCS)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.name} ({self.sku})"


class ProductionEntry(models.Model):
    entry_date = models.DateField(default=timezone.now)
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="entries")
    worker = models.ForeignKey(Worker, on_delete=models.PROTECT, related_name="entries")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="entries")
    target_qty = models.DecimalField(max_digits=12, decimal_places=2)
    actual_qty = models.DecimalField(max_digits=12, decimal_places=2)
    shift_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("8.00"))
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    target_met = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        get_user_model(), on_delete=models.SET_NULL, null=True, blank=True, related_name="production_entries"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-entry_date", "section_id", "worker_id"]
        unique_together = ["entry_date", "section", "worker", "item"]

    def save(self, *args, **kwargs):
        if self.target_qty and self.actual_qty is not None:
            self.target_met = self.actual_qty >= self.target_qty
            if self.target_qty > 0 and self.shift_hours:
                ratio = Decimal(self.actual_qty) / Decimal(self.target_qty)
                overtime = (ratio - Decimal("1")) * Decimal(self.shift_hours)
                self.overtime_hours = max(Decimal("0.00"), overtime.quantize(Decimal("0.01")))
        super().save(*args, **kwargs)

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.entry_date} {self.section} {self.worker} {self.item}"
