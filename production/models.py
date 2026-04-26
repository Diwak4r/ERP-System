from __future__ import annotations

from datetime import date, datetime, time
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


class Machine(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="machines")
    name = models.CharField(max_length=255)
    machine_code = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["section__name", "name"]

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return f"{self.name} ({self.machine_code})"


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
        # Update Ledger post save
        if self.section and self.item and self.entry_date:
            ledger, _ = DailyLedger.objects.get_or_create(
                date=self.entry_date, section=self.section, item=self.item
            )
            # Recompute total output
            total_output = ProductionEntry.objects.filter(
                section=self.section, item=self.item, entry_date=self.entry_date
            ).aggregate(total=models.Sum("actual_qty"))["total"] or Decimal("0.00")

            ledger.output_qty = total_output
            ledger.save(update_fields=["output_qty"])


class WasteEntry(models.Model):
    waste_date = models.DateField()
    section = models.ForeignKey(Section, on_delete=models.PROTECT)
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    waste_qty = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="waste_entries")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-waste_date", "section__name", "item__name"]
        indexes = [
            models.Index(fields=["waste_date", "section", "item"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return f"{self.waste_date} - {self.section} - {self.item} ({self.waste_qty})"

    def clean(self) -> None:
        if self.pk is None and self.waste_date and self.waste_date < date.today():
            raise ValidationError("Cannot create backdated waste entries.")

        if getattr(self, "section", None) and getattr(self, "waste_date", None):
            lock = DayLock.objects.filter(section=self.section, lock_date=self.waste_date, is_locked=True).first()
            if lock:
                raise ValidationError(f"Section {self.section.name} is locked for {self.waste_date}.")

        if getattr(self, "section", None) and getattr(self, "item", None) and getattr(self, "waste_date", None):
            ledger, _ = DailyLedger.objects.get_or_create(date=self.waste_date, section=self.section, item=self.item)
            available = ledger.total_available - ledger.output_qty
            if available < Decimal("0.00"):
                available = Decimal("0.00")

            current_waste_qs = WasteEntry.objects.filter(
                section=self.section,
                item=self.item,
                waste_date=self.waste_date,
            )
            if self.pk:
                current_waste_qs = current_waste_qs.exclude(pk=self.pk)

            current_waste = current_waste_qs.aggregate(total=models.Sum("waste_qty"))["total"] or Decimal("0.00")
            proposed_waste = current_waste + (self.waste_qty or Decimal("0.00"))
            if proposed_waste > available:
                raise ValidationError(
                    f"Waste ({proposed_waste}) exceeds remaining available inventory ({available}) "
                    f"for {self.item} in {self.section.name}."
                )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.section and self.item and self.waste_date:
            ledger, _ = DailyLedger.objects.get_or_create(
                date=self.waste_date,
                section=self.section,
                item=self.item,
            )
            total_waste = WasteEntry.objects.filter(
                section=self.section,
                item=self.item,
                waste_date=self.waste_date,
            ).aggregate(total=models.Sum("waste_qty"))["total"] or Decimal("0.00")
            ledger.waste_qty = total_waste
            ledger.save(update_fields=["waste_qty"])


class AttendanceSheet(models.Model):
    attendance_date = models.DateField()
    section = models.ForeignKey(Section, on_delete=models.PROTECT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_sheets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-attendance_date", "section__name"]
        unique_together = ("attendance_date", "section")
        indexes = [
            models.Index(fields=["attendance_date", "section"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return f"{self.attendance_date} - {self.section}"

    def clean(self) -> None:
        if self.pk is None and self.attendance_date and self.attendance_date < date.today():
            raise ValidationError("Cannot create backdated attendance sheets.")

        if getattr(self, "section", None) and getattr(self, "attendance_date", None):
            lock = DayLock.objects.filter(section=self.section, lock_date=self.attendance_date, is_locked=True).first()
            if lock:
                raise ValidationError(f"Section {self.section.name} is locked for {self.attendance_date}.")

    @property
    def present_count(self) -> int:
        return self.lines.filter(status=AttendanceLine.STATUS_PRESENT).count()


class AttendanceLine(models.Model):
    STATUS_PRESENT = "PRESENT"
    STATUS_ABSENT = "ABSENT"
    STATUS_CHOICES = [
        (STATUS_PRESENT, "Present"),
        (STATUS_ABSENT, "Absent"),
    ]

    sheet = models.ForeignKey(AttendanceSheet, on_delete=models.CASCADE, related_name="lines")
    worker = models.ForeignKey(Worker, on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PRESENT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["worker__name"]
        unique_together = ("sheet", "worker")
        indexes = [
            models.Index(fields=["sheet", "status"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return f"{self.sheet} - {self.worker} ({self.status})"


class MachineDowntime(models.Model):
    machine = models.ForeignKey(Machine, on_delete=models.PROTECT, related_name="downtimes")
    downtime_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(default=0)
    reason = models.TextField()
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="machine_downtimes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-downtime_date", "machine__name", "-start_time"]
        indexes = [
            models.Index(fields=["downtime_date", "machine"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return f"{self.machine} on {self.downtime_date} ({self.start_time}-{self.end_time or 'ongoing'})"

    @staticmethod
    def _duration_in_minutes(start_time: time, end_time: time | None, downtime_date: date) -> int:
        if not end_time:
            return 0
        start_dt = datetime.combine(downtime_date, start_time)
        end_dt = datetime.combine(downtime_date, end_time)
        return int((end_dt - start_dt).total_seconds() // 60)

    def _effective_end(self) -> time:
        return self.end_time or time.max

    def clean(self) -> None:
        if self.end_time and self.end_time <= self.start_time:
            raise ValidationError("End time must be later than start time.")

        if getattr(self, "machine", None) and getattr(self, "downtime_date", None):
            lock = DayLock.objects.filter(
                section=self.machine.section,
                lock_date=self.downtime_date,
                is_locked=True,
            ).first()
            if lock:
                raise ValidationError(f"Section {self.machine.section.name} is locked for {self.downtime_date}.")

        if getattr(self, "machine", None) and getattr(self, "downtime_date", None) and getattr(self, "start_time", None):
            overlapping_entries = MachineDowntime.objects.filter(
                machine=self.machine,
                downtime_date=self.downtime_date,
            )
            if self.pk:
                overlapping_entries = overlapping_entries.exclude(pk=self.pk)

            current_end = self._effective_end()
            for entry in overlapping_entries:
                entry_end = entry._effective_end()
                if self.start_time < entry_end and entry.start_time < current_end:
                    raise ValidationError("Downtime window overlaps an existing entry for this machine.")

        if getattr(self, "downtime_date", None) and getattr(self, "start_time", None):
            self.duration_minutes = self._duration_in_minutes(
                self.start_time,
                self.end_time,
                self.downtime_date,
            )

    def save(self, *args, **kwargs):
        if self.downtime_date and self.start_time:
            self.duration_minutes = self._duration_in_minutes(
                self.start_time,
                self.end_time,
                self.downtime_date,
            )
        super().save(*args, **kwargs)


class Requisition(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="requisitions")
    requested_qty = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requisitions",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviewed_requisitions",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    requested_section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="requisitions",
    )
    requested_date = models.DateField(default=date.today)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["requested_by", "status"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return f"{self.item} - {self.requested_qty} ({self.status})"


class StatusHistory(models.Model):
    requisition = models.ForeignKey(
        Requisition,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    from_status = models.CharField(max_length=10, blank=True, default="")
    to_status = models.CharField(max_length=10)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requisition_status_changes",
    )
    note = models.TextField(blank=True, default="")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at", "-id"]
        indexes = [
            models.Index(fields=["requisition", "changed_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return f"{self.requisition_id}: {self.from_status or 'START'} -> {self.to_status}"


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
        return self.total_available - self.output_qty - self.waste_qty

    @property
    def waste_percentage(self) -> Decimal:
        available = self.total_available
        if available <= Decimal("0.00"):
            return Decimal("0.00")
        return ((self.waste_qty / available) * Decimal("100.00")).quantize(Decimal("0.01"))
