from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from .models import Item, ProductionEntry, Section, TargetRule, Worker

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_user(db):
    User = get_user_model()
    user = User.objects.create_user(username="admin", password="pass", is_superuser=True)
    return user


@pytest.fixture
def supervisor_user(db):
    User = get_user_model()
    user = User.objects.create_user(username="supervisor", password="pass")
    group, _ = Group.objects.get_or_create(name="SUPERVISOR")
    user.groups.add(group)
    return user


@pytest.fixture
def section(supervisor_user):
    section = Section.objects.create(name="Assembly", code="ASM")
    section.supervisors.add(supervisor_user)
    return section


@pytest.fixture
def worker():
    return Worker.objects.create(name="John", employee_code="W001")


@pytest.fixture
def item():
    return Item.objects.create(name="Widget", sku="ITM-001", unit=Item.UNIT_PCS)


@pytest.fixture
def target_rule(section, item):
    return TargetRule.objects.create(section=section, item=item, target_qty=Decimal("100"), shift_hours=Decimal("8"), start_date=date.today())


def test_overtime_calculation():
    overtime = ProductionEntry.compute_overtime(Decimal("120"), Decimal("100"), Decimal("8"))
    assert overtime == Decimal("1.60")


def test_target_snapshot_saved(admin_user, section, worker, item, target_rule, client):
    client.force_login(admin_user)
    resp = client.post(
        reverse("production:entry"),
        data={
            "entry_date": date.today().isoformat(),
            "section": section.id,
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-worker": worker.id,
            "form-0-item": item.id,
            "form-0-target_qty": "0",
            "form-0-actual_qty": "120",
            "form-0-shift_hours": "0",
        },
        follow=True,
    )
    assert resp.status_code == 200
    entry = ProductionEntry.objects.latest("id")
    assert entry.target_qty == target_rule.target_qty
    assert entry.shift_hours == target_rule.shift_hours
    assert entry.overtime_hours == Decimal("1.60")
    assert entry.target_met is True


def test_permissions_enforced(supervisor_user, section, worker, item, client):
    other_section = Section.objects.create(name="Packaging", code="PKG")
    client.force_login(supervisor_user)
    response = client.post(
        reverse("production:entry"),
        data={
            "entry_date": date.today().isoformat(),
            "section": other_section.id,
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-worker": worker.id,
            "form-0-item": item.id,
            "form-0-target_qty": "0",
            "form-0-actual_qty": "10",
            "form-0-shift_hours": "0",
        },
    )
    assert response.status_code == 403
    assert ProductionEntry.objects.count() == 0


def test_production_entry_formset_queries(section, worker, item, admin_user, django_assert_num_queries):
    # Create 5 items with target rules
    items = [item]
    for i in range(4):
        itm = Item.objects.create(name=f"Widget {i}", sku=f"SKU-{i}")
        items.append(itm)
        TargetRule.objects.create(
            section=section,
            item=itm,
            target_qty=Decimal("100"),
            shift_hours=Decimal("8"),
            start_date=date.today(),
        )
    TargetRule.objects.create(
        section=section,
        item=item,
        target_qty=Decimal("100"),
        shift_hours=Decimal("8"),
        start_date=date.today(),
    )

    from .forms import ProductionEntryFormSet

    form_kwargs = {"section": section, "entry_date": date.today()}
    data = {
        "form-TOTAL_FORMS": "5",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
    }
    for i, itm in enumerate(items):
        data[f"form-{i}-worker"] = worker.id
        data[f"form-{i}-item"] = itm.id
        data[f"form-{i}-actual_qty"] = "100"
        data[f"form-{i}-target_qty"] = "100"
        data[f"form-{i}-shift_hours"] = "8"

    # With optimizations, query count should be significantly lower.
    # Baseline for 5 forms was ~26. Current optimized is around 23 for 5 forms.
    with django_assert_num_queries(23):
        formset = ProductionEntryFormSet(data=data, prefix="form", form_kwargs=form_kwargs)
        assert formset.is_valid()
