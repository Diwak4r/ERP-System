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
    def for_section_item_date(self, *, section: Section, target_date: date, item: Item | None = None):
        qs = self.filter(
            section=section,
            start_date__lte=target_date,
        ).filter(models.Q(end_date__gte=target_date) | models.Q(end_date__isnull=True))
        if item:
            qs = qs.filter(item=item)
        return qs.order_by("-start_date")


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
        if self.entry_date and self.section_id:
            from .models import DayLock, ProcessFlowEdge, DailyLedger

            # 1. DayLock check / Strict No Backdate Edits
            if self.entry_date < date.today():
                raise ValidationError("Backdated edits are strictly prohibited.")

            lock = DayLock.objects.filter(section=self.section, lock_date=self.entry_date).first()
            if lock and lock.is_locked:
                raise ValidationError("Cannot create or modify entries for a locked day.")

            # 2. Hard Block Inventory Gate
            # If there are incoming edges, this section is downstream, meaning its output is constrained by inventory
            incoming_edges = ProcessFlowEdge.objects.filter(to_section=self.section, item=self.item).exists()
            if incoming_edges:
                ledger = DailyLedger.objects.filter(date=self.entry_date, section=self.section, item=self.item).first()
                # Determine current output
                current_actual = self.actual_qty or Decimal("0")
                if self.pk:
                    # Subtract the old actual_qty to get the "other" output
                    old_entry = ProductionEntry.objects.get(pk=self.pk)
                    other_output = (ledger.output if ledger else Decimal("0")) - old_entry.actual_qty
                else:
                    other_output = ledger.output if ledger else Decimal("0")

                new_total_output = other_output + current_actual

                # Available inventory is opening + received + manual_received
                # Note: waste is removed from closing balance, but available inventory for production is the sum of these 3
                available = Decimal("0")
                if ledger:
                    available = ledger.opening_balance + ledger.received_from_prev + ledger.manual_received

                if new_total_output > available:
                    raise ValidationError(f"Hard block: Actual quantity exceeds available inventory ({available}).")

    def set_outcomes(self) -> None:
        self.target_met = self.actual_qty >= self.target_qty if self.target_qty is not None else False
        self.overtime_hours = self.compute_overtime(self.actual_qty, self.target_qty, self.shift_hours)

class ProcessFlowEdge(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    from_section = models.ForeignKey(Section, related_name="outgoing_edges", on_delete=models.CASCADE)
    to_section = models.ForeignKey(Section, related_name="incoming_edges", on_delete=models.CASCADE)
    lead_days = models.IntegerField(default=0)

    class Meta:
        unique_together = ("item", "from_section", "to_section")

    def __str__(self) -> str:
        return f"{self.item}: {self.from_section} -> {self.to_section}"


class DayLock(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    lock_date = models.DateField()
    is_locked = models.BooleanField(default=True)
    locked_at = models.DateTimeField(auto_now_add=True)
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = ("section", "lock_date")

    def __str__(self) -> str:
        return f"{self.section} on {self.lock_date} (Locked: {self.is_locked})"


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100)
    before_json = models.JSONField(null=True, blank=True)
    after_json = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]


class DailyLedger(models.Model):
    date = models.DateField()
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)

    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    received_from_prev = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    manual_received = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    output = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    waste = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    closing_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        unique_together = ("date", "section", "item")

    def recompute(self):
        self.closing_balance = self.opening_balance + self.received_from_prev + self.manual_received - self.output - self.waste

    def __str__(self) -> str:
        return f"{self.date} - {self.section} - {self.item} (Bal: {self.closing_balance})"
