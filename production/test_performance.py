from datetime import date
from decimal import Decimal
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from production.models import Section, Item, Worker, TargetRule, ProductionEntry
from production.forms import ProductionEntryForm, ProductionEntryFormSet

@pytest.mark.django_db
def test_production_entry_formset_n_plus_one(django_assert_num_queries):
    User = get_user_model()
    admin_user = User.objects.create_user(username="admin", password="pass", is_superuser=True)
    section = Section.objects.create(name="Assembly", code="ASM")
    worker = Worker.objects.create(name="John", employee_code="W001")
    items = [
        Item.objects.create(name=f"Item {i}", sku=f"SKU-{i}")
        for i in range(10)
    ]
    for item in items:
        TargetRule.objects.create(
            section=section,
            item=item,
            target_qty=Decimal("100"),
            shift_hours=Decimal("8"),
            start_date=date.today()
        )

    form_data = {
        "form-TOTAL_FORMS": "10",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }
    for i, item in enumerate(items):
        form_data[f"form-{i}-worker"] = worker.id
        form_data[f"form-{i}-item"] = item.id
        form_data[f"form-{i}-target_qty"] = "0"
        form_data[f"form-{i}-actual_qty"] = "120"
        form_data[f"form-{i}-shift_hours"] = "0"

    form_kwargs = {"section": section, "entry_date": date.today()}

    # Each form.clean() used to call TargetRule.objects.for_section_item_date(...).first()
    # Now it should use the cache.
    # We still have N+N for worker/item validation.
    # Total queries before: 50
    # Expected queries now: 41
    with django_assert_num_queries(41):
        formset = ProductionEntryFormSet(data=form_data, prefix="form", form_kwargs=form_kwargs)
        assert formset.is_valid()

@pytest.mark.django_db
def test_production_entry_form_fallback(django_assert_num_queries):
    section = Section.objects.create(name="Assembly", code="ASM")
    item = Item.objects.create(name="Widget", sku="WID")
    TargetRule.objects.create(
        section=section,
        item=item,
        target_qty=Decimal("100"),
        shift_hours=Decimal("8"),
        start_date=date.today()
    )

    # Using the form directly without rules_cache should still work (but with a query)
    form_data = {
        "worker": Worker.objects.create(name="John", employee_code="W001").id,
        "item": item.id,
        "target_qty": "0",
        "actual_qty": "120",
        "shift_hours": "0",
    }

    form = ProductionEntryForm(data=form_data, section=section, entry_date=date.today())
    with django_assert_num_queries(5): # 1 for worker, 1 for item, 1 for TargetRule, +2 overhead
        assert form.is_valid()
    assert form.cleaned_data["target_qty"] == Decimal("100")
