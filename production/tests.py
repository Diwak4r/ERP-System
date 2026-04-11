from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
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

def test_daily_section_summary_view(admin_user, section, worker, item, client):
    # Setup some entries
    ProductionEntry.objects.create(
        entry_date=date.today(), section=section, worker=worker, item=item,
        target_qty=Decimal("100"), actual_qty=Decimal("110"), shift_hours=Decimal("8"), created_by=admin_user
    )

    client.force_login(admin_user)
    response = client.get(reverse("production:report-daily-section"))

    assert response.status_code == 200
    assert b"Daily Section Summary" in response.content
    assert b"110" in response.content # Actual qty
    assert str(worker.name).encode() in response.content

def test_item_aggregate_view(admin_user, section, worker, item, client):
    ProductionEntry.objects.create(
        entry_date=date.today(), section=section, worker=worker, item=item,
        target_qty=Decimal("100"), actual_qty=Decimal("110"), shift_hours=Decimal("8"), created_by=admin_user
    )

    client.force_login(admin_user)
    response = client.get(reverse("production:report-item-aggregate"))

    assert response.status_code == 200
    assert b"Item Aggregate Report" in response.content
    assert b"110.0" in response.content # Hit rate

def test_worker_history_view(admin_user, section, worker, item, client):
    ProductionEntry.objects.create(
        entry_date=date.today(), section=section, worker=worker, item=item,
        target_qty=Decimal("100"), actual_qty=Decimal("90"), shift_hours=Decimal("8"),
        created_by=admin_user, target_met=False
    )

    client.force_login(admin_user)
    response = client.get(reverse("production:report-worker-history", args=[worker.id]))

    assert response.status_code == 200
    assert str(worker.name).encode() in response.content
    assert b"90.00" in response.content # Actual qty
def test_daily_section_summary_view_invalid_date(admin_user, section, client):
    client.force_login(admin_user)
    response = client.get(reverse("production:report-daily-section"), {"date": "invalid-date"})
    assert response.status_code == 200

def test_item_aggregate_view_invalid_date(admin_user, section, client):
    client.force_login(admin_user)
    response = client.get(reverse("production:report-item-aggregate"), {"start_date": "invalid", "end_date": "invalid"})
    assert response.status_code == 200

from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import timedelta
from .models import DayLock, DailyLedger, ProcessFlowEdge, AuditEvent

@pytest.mark.django_db
def test_daylock_prevents_creation(supervisor_user, section, worker, item):
    today = date.today()
    DayLock.objects.create(section=section, lock_date=today, is_locked=True)

    entry = ProductionEntry(
        entry_date=today,
        section=section,
        worker=worker,
        item=item,
        target_qty=Decimal("100"),
        actual_qty=Decimal("120"),
        shift_hours=Decimal("8"),
        created_by=supervisor_user
    )
    with pytest.raises(ValidationError, match="Cannot create or modify entries for a locked day"):
        entry.clean()

@pytest.mark.django_db
def test_hard_block_inventory_gate(supervisor_user, section, worker, item):
    today = date.today()
    # Create another section to act as upstream
    section1 = Section.objects.create(name="Section 1", code="S1")

    # Create a flow edge: Section 1 -> Section (downstream)
    ProcessFlowEdge.objects.create(item=item, from_section=section1, to_section=section, lead_days=0)

    # Give the downstream section 100 available units in its ledger
    DailyLedger.objects.create(
        date=today,
        section=section,
        item=item,
        opening_balance=Decimal("100")
    )

    # Try to create 120 actual_qty in the downstream section. Should fail.
    entry = ProductionEntry(
        entry_date=today,
        section=section,
        worker=worker,
        item=item,
        target_qty=Decimal("100"),
        actual_qty=Decimal("120"),
        shift_hours=Decimal("8"),
        created_by=supervisor_user
    )
    with pytest.raises(ValidationError, match="Hard block"):
        entry.clean()

    # Valid amount should pass
    entry.actual_qty = Decimal("80")
    entry.clean() # Should not raise

@pytest.mark.django_db
def test_audit_logging_admin(client, admin_user, section, worker, item):
    today = date.today()

    # Needs to be a superuser or staff to access admin panel
    admin_user.is_staff = True
    admin_user.is_superuser = True
    admin_user.save()

    entry = ProductionEntry.objects.create(
        entry_date=today,
        section=section,
        worker=worker,
        item=item,
        target_qty=Decimal("100"),
        actual_qty=Decimal("50"),
        shift_hours=Decimal("8"),
        created_by=admin_user
    )

    client.force_login(admin_user)

    # Update via admin
    url = f"/admin/production/productionentry/{entry.pk}/change/"
    response = client.post(url, {
        "entry_date": today.isoformat(),
        "section": section.pk,
        "worker": worker.pk,
        "item": item.pk,
        "target_qty": "100",
        "actual_qty": "60",
        "shift_hours": "8",
        "overtime_hours": "0",
        "created_by": admin_user.pk,
        "_save": "Save",
    })

    # Verify AuditEvent was created
    audit = AuditEvent.objects.filter(model_name="ProductionEntry").first()
    assert audit is not None
    assert audit.action == "UPDATE"
    assert Decimal(audit.before_json["actual_qty"]) == Decimal("50.00")
    assert Decimal(audit.after_json["actual_qty"]) == Decimal("60.00")

@pytest.mark.django_db
def test_signal_updates_ledger(supervisor_user, section, worker, item):
    today = date.today()

    entry = ProductionEntry.objects.create(
        entry_date=today,
        section=section,
        worker=worker,
        item=item,
        target_qty=Decimal("100"),
        actual_qty=Decimal("50"),
        shift_hours=Decimal("8"),
        created_by=supervisor_user
    )

    ledger = DailyLedger.objects.get(date=today, section=section, item=item)
    assert ledger.output == Decimal("50.00")

    # Create another entry
    ProductionEntry.objects.create(
        entry_date=today,
        section=section,
        worker=worker,
        item=item,
        target_qty=Decimal("100"),
        actual_qty=Decimal("25"),
        shift_hours=Decimal("8"),
        created_by=supervisor_user
    )

    ledger.refresh_from_db()
    assert ledger.output == Decimal("75.00")
