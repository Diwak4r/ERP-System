import pytest
from datetime import date
from decimal import Decimal
from django.urls import reverse
from .models import Section, Worker, Item, TargetRule, ProductionEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

pytestmark = pytest.mark.django_db

@pytest.fixture
def admin_user(db):
    User = get_user_model()
    return User.objects.create_superuser(username="admin", password="pass")

@pytest.fixture
def section():
    return Section.objects.create(name="Assembly", code="ASM")

@pytest.fixture
def workers(db):
    return [Worker.objects.create(name=f"Worker {i}", employee_code=f"W{i:03d}") for i in range(10)]

@pytest.fixture
def items(db):
    return [Item.objects.create(name=f"Item {i}", sku=f"ITM-{i:03d}") for i in range(10)]

@pytest.fixture
def target_rules(section, items):
    rules = []
    for item in items:
        rules.append(TargetRule.objects.create(
            section=section,
            item=item,
            target_qty=Decimal("100"),
            shift_hours=Decimal("8"),
            start_date=date.today()
        ))
    return rules

def test_production_entry_post_query_count(admin_user, section, workers, items, target_rules, client, django_assert_num_queries):
    client.force_login(admin_user)

    data = {
        "entry_date": date.today().isoformat(),
        "section": section.id,
        "form-TOTAL_FORMS": "10",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }
    for i in range(10):
        data[f"form-{i}-worker"] = workers[i].id
        data[f"form-{i}-item"] = items[i].id
        data[f"form-{i}-actual_qty"] = "100"
        data[f"form-{i}-target_qty"] = "0"
        data[f"form-{i}-shift_hours"] = "0"

    # We expect some number of queries.
    # 1. Session lookup
    # 2. User lookup
    # 3. Group check (if any)
    # 4. Section lookup
    # 5. Permission check (supervisors)
    # 6. For each form:
    #    a. Worker exists check (ModelChoiceField)
    #    b. Item exists check (ModelChoiceField)
    #    c. TargetRule lookup
    # 7. For each form (save):
    #    a. ProductionEntry insert
    # 8. Success message/redirect?

    with django_assert_num_queries(33):
        response = client.post(reverse("production:entry"), data=data)
        assert response.status_code == 302
