import os
import django
from datetime import date
from decimal import Decimal
from django.db import connection
from django.test import RequestFactory, utils

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from production.models import Section, Worker, Item, TargetRule, ProductionEntry
from production.forms import ProductionEntryFormSet

def setup_data():
    User = get_user_model()
    admin = User.objects.get_or_create(username="admin", is_superuser=True)[0]

    section = Section.objects.get_or_create(name="Assembly", code="ASM")[0]

    workers = []
    for i in range(10):
        w = Worker.objects.get_or_create(name=f"Worker {i}", employee_code=f"W{i}")[0]
        workers.append(w)

    items = []
    for i in range(5):
        it = Item.objects.get_or_create(name=f"Item {i}", sku=f"SKU{i}")[0]
        items.append(it)
        TargetRule.objects.get_or_create(
            section=section, item=it,
            target_qty=Decimal("100"), shift_hours=Decimal("8"),
            start_date=date(2023, 1, 1)
        )

    return section, workers, items

def run_benchmark():
    section, workers, items = setup_data()
    entry_date = date.today()

    # Simulate POST data for 10 forms
    post_data = {
        "form-TOTAL_FORMS": "10",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }
    for i in range(10):
        post_data[f"form-{i}-worker"] = workers[i].id
        post_data[f"form-{i}-item"] = items[i % 5].id
        post_data[f"form-{i}-target_qty"] = "0"
        post_data[f"form-{i}-actual_qty"] = "120"
        post_data[f"form-{i}-shift_hours"] = "0"

    print("--- Rendering Benchmark ---")
    with utils.CaptureQueriesContext(connection) as ctx:
        formset = ProductionEntryFormSet(prefix="form", form_kwargs={"section": section, "entry_date": entry_date})
        # Trigger rendering of fields that might cause queries (like worker/item choices)
        for form in formset:
            str(form["worker"])
            str(form["item"])
    print(f"Queries during rendering 10 empty forms: {len(ctx)}")

    print("\n--- Validation Benchmark ---")
    with utils.CaptureQueriesContext(connection) as ctx:
        formset = ProductionEntryFormSet(post_data, prefix="form", form_kwargs={"section": section, "entry_date": entry_date})
        is_valid = formset.is_valid()
    print(f"Formset is valid: {is_valid}")
    print(f"Queries during validation of 10 forms: {len(ctx)}")

if __name__ == "__main__":
    run_benchmark()
