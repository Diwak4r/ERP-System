import os
import django
from datetime import date
from decimal import Decimal

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django.contrib.auth import get_user_model
from production.models import Section, Worker, Item, TargetRule, ProductionEntry
from production.forms import ProductionEntryFormSet

User = get_user_model()

def benchmark_formset():
    # Setup data
    User.objects.all().delete()
    Section.objects.all().delete()
    Worker.objects.all().delete()
    Item.objects.all().delete()

    admin = User.objects.create_superuser(username="admin", password="password", email="admin@example.com")
    section = Section.objects.create(name="Assembly", code="ASM")
    worker = Worker.objects.create(name="John Doe", employee_code="W001")
    item = Item.objects.create(name="Widget", sku="ITM-001")
    TargetRule.objects.create(section=section, item=item, target_qty=Decimal("100"), shift_hours=Decimal("8"), start_date=date.today())

    # Create multiple workers and items to make it more realistic
    workers = [worker]
    for i in range(2, 11):
        workers.append(Worker.objects.create(name=f"Worker {i}", employee_code=f"W{i:03d}"))

    items = [item]
    for i in range(2, 6):
        items.append(Item.objects.create(name=f"Item {i}", sku=f"ITM-{i:03d}"))

    form_kwargs = {"section": section, "entry_date": date.today()}

    print("--- Measuring FormSet Initialization ---")
    connection.queries_log.clear()
    formset = ProductionEntryFormSet(prefix="form", form_kwargs=form_kwargs)
    # Trigger rendering/initialization of choices
    for form in formset:
        list(form.fields["worker"].choices)
        list(form.fields["item"].choices)

    print(f"Number of queries for initialization (1 form): {len(connection.queries)}")

    # Measure with 10 forms
    data = {
        "form-TOTAL_FORMS": "10",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }
    for i in range(10):
        data[f"form-{i}-worker"] = workers[i].id
        data[f"form-{i}-item"] = items[0].id
        data[f"form-{i}-actual_qty"] = "100"
        data[f"form-{i}-target_qty"] = "0"
        data[f"form-{i}-shift_hours"] = "8"

    print("\n--- Measuring FormSet Validation ---")
    connection.queries_log.clear()
    formset = ProductionEntryFormSet(data, prefix="form", form_kwargs=form_kwargs)
    is_valid = formset.is_valid()
    print(f"Is valid: {is_valid}")
    if not is_valid:
        print(formset.errors)
    print(f"Number of queries for validation (10 forms): {len(connection.queries)}")
    # for q in connection.queries:
    #    print(q['sql'])

if __name__ == "__main__":
    benchmark_formset()
