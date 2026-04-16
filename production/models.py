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
        # Anti-Excel Immutability Rule
        if self.pk is None and self.entry_date and self.entry_date < date.today():
            raise ValidationError("Cannot create backdated production entries.")

        # Check if the day is locked
        if getattr(self, "section", None) and getattr(self, "entry_date", None):
            lock = DayLock.objects.filter(section=self.section, lock_date=self.entry_date, is_locked=True).first()
            if lock:
                raise ValidationError(f"Section {self.section.name} is locked for {self.entry_date}.")

        # Hard Block Inventory Gate
        if getattr(self, "section", None) and getattr(self, "item", None) and getattr(self, "entry_date", None):
            # Is there an inbound edge for this item to this section?
            inbound_edge = ProcessFlowEdge.objects.filter(item=self.item, to_section=self.section).first()
            if inbound_edge:
                # Calculate available inventory
                ledger, _ = DailyLedger.objects.get_or_create(
                    date=self.entry_date, section=self.section, item=self.item
                )
                available = ledger.opening_balance + ledger.received_from_prev + ledger.manual_received

                # Get current total output for this section/item/date excluding this entry
                current_output_qs = ProductionEntry.objects.filter(
                    section=self.section, item=self.item, entry_date=self.entry_date
                )
                if self.pk:
                    current_output_qs = current_output_qs.exclude(pk=self.pk)

                current_output = current_output_qs.aggregate(total=models.Sum("actual_qty"))["total"] or Decimal("0.00")
                proposed_output = current_output + (self.actual_qty or Decimal("0.00"))

                if proposed_output > available:
                    raise ValidationError(
                        f"Hard Block: Output ({proposed_output}) exceeds available inventory ({available}) "
                        f"for {self.item} in {self.section.name}."
                    )

    def set_outcomes(self) -> None:
        self.target_met = self.actual_qty >= self.target_qty if self.target_qty is not None else False
        self.overtime_hours = self.compute_overtime(self.actual_qty, self.target_qty, self.shift_hours)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.section and self.item and self.entry_date:
            recompute_ledger(self.entry_date, self.section, self.item)

    def delete(self, *args, **kwargs):
        section = self.section
        item = self.item
        entry_date = self.entry_date
        super().delete(*args, **kwargs)
        if section and item and entry_date:
            recompute_ledger(entry_date, section, item)

class DayLock(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    lock_date = models.DateField()
    locked_at = models.DateTimeField(auto_now_add=True)
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    is_locked = models.BooleanField(default=True)

    class Meta:
        unique_together = ("section", "lock_date")
        ordering = ["-lock_date", "section__name"]

    def __str__(self) -> str:
        return f"{self.section} on {self.lock_date} ({'Locked' if self.is_locked else 'Unlocked'})"

class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50) # e.g., 'CREATE', 'UPDATE', 'DELETE', 'UNLOCK'
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=255)
    before_data = models.JSONField(null=True, blank=True)
    after_data = models.JSONField(null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.action} on {self.model_name} by {self.actor} at {self.timestamp}"

class ProcessFlowEdge(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    from_section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="outbound_edges")
    to_section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="inbound_edges")
    lead_days = models.IntegerField(default=0)

    class Meta:
        unique_together = ("item", "from_section", "to_section")
        ordering = ["item__name", "from_section__name"]

    def __str__(self) -> str:
        return f"{self.item}: {self.from_section} -> {self.to_section} ({self.lead_days} days)"

class DailyLedger(models.Model):
    date = models.DateField()
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)

    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    received_from_prev = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    manual_received = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    output_qty = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    waste_qty = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        unique_together = ("date", "section", "item")
        ordering = ["-date", "section__name", "item__name"]

    def __str__(self) -> str:
        return f"{self.date} - {self.section} - {self.item}"


    @property
    def total_available(self) -> Decimal:
        return self.opening_balance + self.received_from_prev + self.manual_received

    @property
    def closing_balance(self) -> Decimal:
        return self.opening_balance + self.received_from_prev + self.manual_received - self.output_qty - self.waste_qty


def recompute_ledger(target_date: date, section: Section, item: Item) -> None:
    ledger, _ = DailyLedger.objects.get_or_create(
        date=target_date, section=section, item=item
    )
    total_output = ProductionEntry.objects.filter(
        section=section, item=item, entry_date=target_date
    ).aggregate(total=models.Sum("actual_qty"))["total"] or Decimal("0.00")

    ledger.output_qty = total_output
    ledger.save(update_fields=["output_qty"])

    edges = ProcessFlowEdge.objects.filter(from_section=section, item=item)
    for edge in edges:
        from datetime import timedelta
        downstream_date = target_date + timedelta(days=edge.lead_days)

        inbound_edges = ProcessFlowEdge.objects.filter(to_section=edge.to_section, item=item)
        total_received = Decimal("0.00")
        for in_edge in inbound_edges:
            upstream_date = downstream_date - timedelta(days=in_edge.lead_days)
            up_ledger = DailyLedger.objects.filter(date=upstream_date, section=in_edge.from_section, item=item).first()
            if up_ledger:
                total_received += up_ledger.output_qty

        downstream_ledger, _ = DailyLedger.objects.get_or_create(
            date=downstream_date, section=edge.to_section, item=item
        )
        downstream_ledger.received_from_prev = total_received
        downstream_ledger.save(update_fields=["received_from_prev"])
