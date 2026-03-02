import pytest
from django.urls import reverse
from production.models import Section, Worker, Item, TargetRule
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model

@pytest.fixture
def admin_user(db):
    User = get_user_model()
    return User.objects.create_user(username="admin", password="pass", is_superuser=True)

@pytest.mark.django_db
def test_production_entry_n_plus_1(client, django_assert_num_queries, admin_user):
    section = Section.objects.create(name="S1", code="S1")
    worker = Worker.objects.create(name="W1", employee_code="W1")
    num_items = 5
    items = [Item.objects.create(name=f"I{i}", sku=f"I{i}") for i in range(num_items)]
    for item in items:
        TargetRule.objects.create(section=section, item=item, target_qty=100, shift_hours=8, start_date=date.today())

    client.force_login(admin_user)

    data = {
        "entry_date": date.today().isoformat(),
        "section": section.id,
        "form-TOTAL_FORMS": str(num_items),
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }
    for i, item in enumerate(items):
        data[f"form-{i}-worker"] = worker.id
        data[f"form-{i}-item"] = item.id
        data[f"form-{i}-target_qty"] = "0"
        data[f"form-{i}-actual_qty"] = "100"
        data[f"form-{i}-shift_hours"] = "0"

    # Baseline was 33 for 5 items, now it's 25
    with django_assert_num_queries(25):
        client.post(reverse("production:entry"), data=data)

@pytest.mark.django_db
def test_production_entry_n_plus_1_more(client, django_assert_num_queries, admin_user):
    section = Section.objects.create(name="S1", code="S1")
    worker = Worker.objects.create(name="W1", employee_code="W1")
    num_items = 10
    items = [Item.objects.create(name=f"I{i}", sku=f"I{i}") for i in range(num_items)]
    for item in items:
        TargetRule.objects.create(section=section, item=item, target_qty=100, shift_hours=8, start_date=date.today())

    client.force_login(admin_user)

    data = {
        "entry_date": date.today().isoformat(),
        "section": section.id,
        "form-TOTAL_FORMS": str(num_items),
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }
    for i, item in enumerate(items):
        data[f"form-{i}-worker"] = worker.id
        data[f"form-{i}-item"] = item.id
        data[f"form-{i}-target_qty"] = "0"
        data[f"form-{i}-actual_qty"] = "100"
        data[f"form-{i}-shift_hours"] = "0"

    # Baseline was 63 for 10 items, now it's 45
    with django_assert_num_queries(45):
        client.post(reverse("production:entry"), data=data)
