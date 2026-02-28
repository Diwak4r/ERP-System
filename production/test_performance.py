import pytest
from datetime import date
from decimal import Decimal
from django.urls import reverse
from .models import Section, Worker, Item, TargetRule, ProductionEntry
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

def create_setup(num_workers):
    User = get_user_model()
    admin, _ = User.objects.get_or_create(username="admin_perf", is_superuser=True)

    section, _ = Section.objects.get_or_create(name="Assembly", code="ASM")
    workers = [Worker.objects.get_or_create(name=f"Worker {i}", employee_code=f"W{i}")[0] for i in range(num_workers)]
    item, _ = Item.objects.get_or_create(name="Widget", sku="ITM-001")

    TargetRule.objects.get_or_create(
        section=section, item=item, target_qty=Decimal("100"),
        shift_hours=Decimal("8"), start_date=date.today()
    )
    return admin, section, workers, item

def get_data(section, workers, item, num):
    data = {
        "entry_date": date.today().isoformat(),
        "section": section.id,
        "form-TOTAL_FORMS": str(num),
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }
    for i in range(num):
        data[f"form-{i}-worker"] = workers[i].id
        data[f"form-{i}-item"] = item.id
        data[f"form-{i}-actual_qty"] = "100"
        data[f"form-{i}-target_qty"] = "0"
        data[f"form-{i}-shift_hours"] = "0"
    return data

@pytest.mark.django_db
def test_production_entry_n_plus_1(client):
    admin, section, workers, item = create_setup(10)
    client.force_login(admin)

    # 1 form
    data_1 = get_data(section, workers, item, 1)
    with CaptureQueriesContext(connection) as captured_1:
        client.post(reverse("production:entry"), data=data_1)

    # 10 forms
    data_10 = get_data(section, workers, item, 10)
    with CaptureQueriesContext(connection) as captured_10:
        client.post(reverse("production:entry"), data=data_10)

    num_1 = len(captured_1)
    num_10 = len(captured_10)

    print(f"\nQueries for 1 entry: {num_1}")
    print(f"Queries for 10 entries: {num_10}")

    # After optimization:
    # 1 entry: 9 queries
    # 10 entries: 45 queries
    # (Previously it was 63 for 10 entries)

    assert num_10 < 63
