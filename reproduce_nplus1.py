import os
import django
from datetime import date
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from production.models import Section, Worker, Item, TargetRule, ProductionEntry
from production.forms import ProductionEntryFormSet
from django.db import connection, reset_queries

User = get_user_model()

def setup_data():
    # Clean up
    TargetRule.objects.all().delete()
    ProductionEntry.objects.all().delete()
    Worker.objects.all().delete()
    Item.objects.all().delete()
    Section.objects.all().delete()
    User.objects.all().delete()

    admin = User.objects.create_superuser("admin", "admin@example.com", "pass")
    section = Section.objects.create(name="Assembly", code="ASM")

    workers = [Worker.objects.create(name=f"Worker {i}", employee_code=f"W{i}") for i in range(10)]
    items = [Item.objects.create(name=f"Item {i}", sku=f"I{i}") for i in range(10)]

    for item in items:
        TargetRule.objects.create(
            section=section,
            item=item,
            target_qty=Decimal("100"),
            shift_hours=Decimal("8"),
            start_date=date(2023, 1, 1)
        )

    return admin, section, workers, items

def benchmark():
    admin, section, workers, items = setup_data()

    entry_date = date(2023, 10, 27)

    # Simulate a POST request with 10 rows
    data = {
        "form-TOTAL_FORMS": "10",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }
    for i in range(10):
        data[f"form-{i}-worker"] = workers[i].id
        data[f"form-{i}-item"] = items[i].id
        data[f"form-{i}-target_qty"] = "0" # Should be hydrated
        data[f"form-{i}-actual_qty"] = "100"
        data[f"form-{i}-shift_hours"] = "0" # Should be hydrated

    form_kwargs = {"section": section, "entry_date": entry_date}

    reset_queries()
    formset = ProductionEntryFormSet(data, prefix="form", form_kwargs=form_kwargs)

    print(f"Validating formset with 10 rows...")
    is_valid = formset.is_valid()
    print(f"Is valid: {is_valid}")

    query_count = len(connection.queries)
    print(f"Total queries during validation: {query_count}")

    for q in connection.queries:
        print(q['sql'])

if __name__ == "__main__":
    benchmark()
