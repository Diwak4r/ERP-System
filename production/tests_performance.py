from datetime import date
from decimal import Decimal
import pytest
from django.contrib.auth import get_user_model
from .models import Item, Section, TargetRule, Worker
from .forms import ProductionEntryFormSet

pytestmark = pytest.mark.django_db

@pytest.fixture
def supervisor_user(db):
    User = get_user_model()
    return User.objects.create_user(username="supervisor", password="pass")

@pytest.fixture
def section(supervisor_user):
    section = Section.objects.create(name="Assembly", code="ASM")
    section.supervisors.add(supervisor_user)
    return section

@pytest.fixture
def workers():
    return [
        Worker.objects.create(name=f"Worker {i}", employee_code=f"W00{i}")
        for i in range(1, 6)
    ]

@pytest.fixture
def items():
    return [
        Item.objects.create(name=f"Item {i}", sku=f"ITM-00{i}", unit=Item.UNIT_PCS)
        for i in range(1, 6)
    ]

@pytest.fixture
def target_rules(section, items):
    return [
        TargetRule.objects.create(
            section=section,
            item=item,
            target_qty=Decimal("100"),
            shift_hours=Decimal("8"),
            start_date=date.today()
        )
        for item in items
    ]

def test_formset_validation_query_count(django_assert_num_queries, section, workers, items, target_rules):
    # Prepare data for 5 rows
    data = {
        "form-TOTAL_FORMS": "5",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }
    for i in range(5):
        data[f"form-{i}-worker"] = workers[i].id
        data[f"form-{i}-item"] = items[i].id
        data[f"form-{i}-target_qty"] = "0"
        data[f"form-{i}-actual_qty"] = "100"
        data[f"form-{i}-shift_hours"] = "0"

    entry_date = date.today()
    form_kwargs = {"section": section, "entry_date": entry_date}

    formset = ProductionEntryFormSet(data, prefix="form", form_kwargs=form_kwargs)

    # OPTIMIZED: Expected to be 20 queries for 5 rows
    # 1x TargetRule lookup (pre-fetched in BaseProductionEntryFormSet constructor)
    # The following happen inside formset.is_valid():
    # 5x Worker existence check (ModelChoiceField)
    # 5x Item existence check (ModelChoiceField)
    # 5x Worker queryset lookup in form.__init__
    # 4x Item queryset lookup in form.__init__ (one might be cached or skipped)
    # Total: 1 + 5 + 5 + 5 + 4 = 20 (Actual measured)
    with django_assert_num_queries(20):
        assert formset.is_valid()
