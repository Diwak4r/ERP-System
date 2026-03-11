import pytest
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from production.models import Section, Worker, Item, TargetRule
from production.forms import ProductionEntryFormSet

@pytest.mark.django_db
def test_production_entry_formset_performance(django_assert_num_queries):
    # Setup
    section = Section.objects.create(name="Benchmark Section", code="BMK")
    workers = [Worker.objects.create(name=f"Worker {i}", employee_code=f"W{i}") for i in range(10)]
    items = [Item.objects.create(name=f"Item {i}", sku=f"I{i}") for i in range(5)]

    for item in items:
        TargetRule.objects.create(section=section, item=item, target_qty=Decimal("100"), shift_hours=Decimal("8"), start_date=date.today())

    # Data for 10 forms
    data = {
        "form-TOTAL_FORMS": "10",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }
    for i in range(10):
        data[f"form-{i}-worker"] = workers[i].id
        data[f"form-{i}-item"] = items[i % 5].id
        data[f"form-{i}-target_qty"] = "0"
        data[f"form-{i}-actual_qty"] = "120"
        data[f"form-{i}-shift_hours"] = "0"

    form_kwargs = {"section": section, "entry_date": date.today()}

    # We want to measure queries during is_valid()
    formset = ProductionEntryFormSet(data, prefix="form", form_kwargs=form_kwargs)

    # Optimized check
    # 3 initial pre-fetch queries (TargetRule, Worker, Item)
    # 20 validation queries (1 worker check + 1 item check per form)
    with django_assert_num_queries(23):
        assert formset.is_valid()
