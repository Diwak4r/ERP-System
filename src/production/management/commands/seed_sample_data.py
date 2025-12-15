from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from production.models import Item, ProductionEntry, Section, Worker


class Command(BaseCommand):
    help = "Seed sample production data for demos"

    def handle(self, *args, **options):
        section, _ = Section.objects.get_or_create(name="Assembly", code="ASM")
        worker1, _ = Worker.objects.get_or_create(name="Alice", employee_code="W1")
        worker2, _ = Worker.objects.get_or_create(name="Bob", employee_code="W2")
        item1, _ = Item.objects.get_or_create(name="Widget", sku="ITM1")
        item2, _ = Item.objects.get_or_create(name="Gadget", sku="ITM2")

        today = date.today()
        ProductionEntry.objects.get_or_create(
            entry_date=today,
            section=section,
            worker=worker1,
            item=item1,
            defaults={
                "target_qty": Decimal("100"),
                "actual_qty": Decimal("110"),
                "shift_hours": Decimal("8"),
            },
        )
        ProductionEntry.objects.get_or_create(
            entry_date=today,
            section=section,
            worker=worker2,
            item=item2,
            defaults={
                "target_qty": Decimal("80"),
                "actual_qty": Decimal("70"),
                "shift_hours": Decimal("8"),
            },
        )
        self.stdout.write(self.style.SUCCESS("Seeded sample data."))
