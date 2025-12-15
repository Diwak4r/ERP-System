from datetime import date
from decimal import Decimal

from django.db.models import Case, Count, Sum, When
from django.test import TestCase

from .models import Item, ProductionEntry, Section, Worker


class ReportAggregationTests(TestCase):
    def setUp(self):
        self.section = Section.objects.create(name="Assembly", code="ASM")
        self.worker1 = Worker.objects.create(name="Alice", employee_code="W1")
        self.worker2 = Worker.objects.create(name="Bob", employee_code="W2")
        self.item1 = Item.objects.create(name="Widget", sku="ITM1")
        self.item2 = Item.objects.create(name="Gadget", sku="ITM2")

        ProductionEntry.objects.create(
            entry_date=date(2024, 1, 1),
            section=self.section,
            worker=self.worker1,
            item=self.item1,
            target_qty=Decimal("100"),
            actual_qty=Decimal("110"),
            shift_hours=Decimal("8"),
        )
        ProductionEntry.objects.create(
            entry_date=date(2024, 1, 1),
            section=self.section,
            worker=self.worker2,
            item=self.item1,
            target_qty=Decimal("50"),
            actual_qty=Decimal("40"),
            shift_hours=Decimal("8"),
        )
        ProductionEntry.objects.create(
            entry_date=date(2024, 1, 1),
            section=self.section,
            worker=self.worker2,
            item=self.item2,
            target_qty=Decimal("60"),
            actual_qty=Decimal("60"),
            shift_hours=Decimal("8"),
        )
        ProductionEntry.objects.create(
            entry_date=date(2024, 1, 2),
            section=self.section,
            worker=self.worker1,
            item=self.item1,
            target_qty=Decimal("120"),
            actual_qty=Decimal("90"),
            shift_hours=Decimal("8"),
        )

    def test_daily_section_totals(self):
        entries = ProductionEntry.objects.filter(entry_date=date(2024, 1, 1), section=self.section)
        per_item = entries.values("item__name").annotate(total_actual_sum=Sum("actual_qty"))
        totals = {row["item__name"]: row["total_actual_sum"] for row in per_item}
        self.assertEqual(totals["Widget"], Decimal("150"))
        self.assertEqual(totals["Gadget"], Decimal("60"))
        worker_count = entries.values("worker_id").distinct().count()
        self.assertEqual(worker_count, 2)

    def test_item_aggregate_hit_rate(self):
        entries = ProductionEntry.objects.filter(entry_date=date(2024, 1, 1), section=self.section)
        aggregate = (
            entries.values("item__name")
            .annotate(
                total_target=Sum("target_qty"),
                total_actual=Sum("actual_qty"),
                hits=Sum(Case(When(target_met=True, then=1), default=0)),
                entry_count=Count("id"),
            )
            .order_by("item__name")
        )
        widget = next(row for row in aggregate if row["item__name"] == "Widget")
        self.assertEqual(widget["total_target"], Decimal("150"))
        self.assertEqual(widget["total_actual"], Decimal("150"))
        self.assertEqual(widget["hits"], 1)
        self.assertEqual(widget["entry_count"], 2)

    def test_worker_history_daily_totals(self):
        start = date(2024, 1, 1)
        end = date(2024, 1, 2)
        entries = ProductionEntry.objects.filter(
            entry_date__range=(start, end), section=self.section, worker=self.worker1
        )
        per_day = entries.values("entry_date").annotate(total_target=Sum("target_qty"), total_actual=Sum("actual_qty"))
        totals = {row["entry_date"]: (row["total_target"], row["total_actual"]) for row in per_day}
        self.assertEqual(totals[date(2024, 1, 1)], (Decimal("100"), Decimal("110")))
        self.assertEqual(totals[date(2024, 1, 2)], (Decimal("120"), Decimal("90")))
