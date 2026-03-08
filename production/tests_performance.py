import pytest
from datetime import date
from decimal import Decimal
from django.urls import reverse
from production.models import Section, Worker, Item, TargetRule, ProductionEntry

@pytest.fixture
def data_setup(db):
    section = Section.objects.create(name="Assembly", code="ASM")
    workers = [Worker.objects.create(name=f"Worker {i}", employee_code=f"W{i}") for i in range(5)]
    items = [Item.objects.create(name=f"Item {i}", sku=f"SKU{i}") for i in range(5)]
    for item in items:
        TargetRule.objects.create(
            section=section,
            item=item,
            target_qty=Decimal("100"),
            shift_hours=Decimal("8"),
            start_date=date.today()
        )
    return section, workers, items

@pytest.mark.django_db
def test_production_entry_formset_query_count(client, admin_user, data_setup, django_assert_num_queries):
    section, workers, items = data_setup
    client.force_login(admin_user)

    # We want to measure the number of queries for a formset with 5 forms
    form_data = {
        "entry_date": date.today().isoformat(),
        "section": section.id,
        "form-TOTAL_FORMS": "5",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }
    for i in range(5):
        form_data.update({
            f"form-{i}-worker": workers[i].id,
            f"form-{i}-item": items[i].id,
            f"form-{i}-target_qty": "0",
            f"form-{i}-actual_qty": "100",
            f"form-{i}-shift_hours": "0",
        })

    # Baseline was 33 queries for 5 forms.
    # Optimization saved 4 queries by bulk-fetching TargetRules (5 -> 1).
    with django_assert_num_queries(29):
        response = client.post(reverse("production:entry"), data=form_data)
        assert response.status_code == 302
