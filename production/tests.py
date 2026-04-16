from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.contrib.admin.sites import AdminSite
from django.urls import reverse

from .admin import ProductionEntryAdmin
from .models import Item, ProductionEntry, Section, TargetRule, Worker, DayLock, ProcessFlowEdge, DailyLedger, AuditEvent

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

@pytest.mark.django_db
def test_daylock_prevents_backdated_edits(admin_user, section, worker, item):
    today = date.today()
    past_date = today - timedelta(days=2)

    # Test Anti-Excel rule (Backdate without lock)
    pe1 = ProductionEntry(entry_date=past_date, section=section, worker=worker, item=item, target_qty=10, actual_qty=5, shift_hours=8, created_by=admin_user)
    with pytest.raises(ValidationError, match="Cannot create backdated production entries."):
        pe1.clean()

    # Test DayLock block
    DayLock.objects.create(section=section, lock_date=today, is_locked=True)
    pe2 = ProductionEntry(entry_date=today, section=section, worker=worker, item=item, target_qty=10, actual_qty=5, shift_hours=8, created_by=admin_user)
    with pytest.raises(ValidationError, match=f"Section {section.name} is locked for {today}."):
        pe2.clean()

@pytest.mark.django_db
def test_hard_block_inventory_gate(admin_user, worker, item):
    today = date.today()
    sec1 = Section.objects.create(name="Sec1", code="S1")
    sec2 = Section.objects.create(name="Sec2", code="S2")

    ProcessFlowEdge.objects.create(item=item, from_section=sec1, to_section=sec2)
    DailyLedger.objects.create(date=today, section=sec2, item=item, opening_balance=Decimal("10.00"))

    # Output 15 > Inventory 10
    pe = ProductionEntry(entry_date=today, section=sec2, worker=worker, item=item, target_qty=10, actual_qty=15, shift_hours=8, created_by=admin_user)
    with pytest.raises(ValidationError, match="Hard Block: Output"):
        pe.clean()

@pytest.mark.django_db
def test_audit_event_created_on_admin_edit(admin_user, section, worker, item):
    request_factory = RequestFactory()
    request = request_factory.post('/admin/')
    request.user = admin_user

    admin_site = AdminSite()
    pe_admin = ProductionEntryAdmin(ProductionEntry, admin_site)

    entry = ProductionEntry.objects.create(entry_date=date.today(), section=section, worker=worker, item=item, target_qty=10, actual_qty=5, shift_hours=8, created_by=admin_user)

    # Trigger save_model manually to simulate Admin Update
    entry.actual_qty = 10
    pe_admin.save_model(request, entry, None, change=True)

    assert AuditEvent.objects.filter(model_name="ProductionEntry", action="UPDATE").count() == 1

@pytest.mark.django_db
def test_recompute_ledger_cascades(admin_user, worker, item):
    today = date.today()
    sec1 = Section.objects.create(name="Mixing", code="MIX")
    sec2 = Section.objects.create(name="Baking", code="BAK")
    ProcessFlowEdge.objects.create(item=item, from_section=sec1, to_section=sec2, lead_days=0)

    # Output in sec1
    ProductionEntry.objects.create(
        entry_date=today, section=sec1, worker=worker, item=item,
        target_qty=100, actual_qty=50, shift_hours=8, created_by=admin_user
    )

    # Check sec1 ledger output
    l1 = DailyLedger.objects.get(date=today, section=sec1, item=item)
    assert l1.output_qty == Decimal("50.00")

    # Check sec2 ledger received
    l2 = DailyLedger.objects.get(date=today, section=sec2, item=item)
    assert l2.received_from_prev == Decimal("50.00")
    assert l2.total_available == Decimal("50.00")

@pytest.mark.django_db
def test_ledger_anomaly_flagging(admin_user, worker, item, client):
    today = date.today()
    sec1 = Section.objects.create(name="Mixing", code="MIX")
    DailyLedger.objects.create(date=today, section=sec1, item=item, opening_balance=Decimal("10.00"))

    # Create output larger than available. We must bypass form validation to force the DB state for the view test
    # but clean() will stop us. Let's just create the ledger manually.
    l1 = DailyLedger.objects.get(date=today, section=sec1, item=item)
    l1.output_qty = Decimal("20.00")
    l1.save()

    client.force_login(admin_user)
    resp = client.get(reverse("production:ledger"))
    assert resp.status_code == 200
    assert b"table-danger" in resp.content
    assert b"Anomaly!" in resp.content

@pytest.mark.django_db
def test_waste_entry_form(admin_user, worker, item, client):
    today = date.today()
    sec1 = Section.objects.create(name="Mixing", code="MIX")
    DailyLedger.objects.create(date=today, section=sec1, item=item, opening_balance=Decimal("10.00"), waste_qty=Decimal("0.00"))

    client.force_login(admin_user)
    # Get the form to get management form data
    resp = client.get(reverse("production:waste-entry"))

    # Check that the form displays the ledger row correctly
    assert resp.status_code == 200
    assert b"Widget" in resp.content

    # The form prefix is 'form' by default for modelformset_factory. We need to parse what we get.
    # But since we only have one ledger, we know form-TOTAL_FORMS = 1
    resp = client.post(reverse("production:waste-entry"), data={
        "date": today.isoformat(),
        "section": sec1.id,
        "form-TOTAL_FORMS": "1",
        "form-INITIAL_FORMS": "1",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
        "form-0-id": DailyLedger.objects.get(date=today, section=sec1, item=item).id,
        "form-0-waste_qty": "2.50",
    })

    # Follow redirect
    assert resp.status_code in [302, 200]

    l1 = DailyLedger.objects.get(date=today, section=sec1, item=item)
    assert l1.waste_qty == Decimal("2.50")
    assert l1.closing_balance == Decimal("7.50")

@pytest.mark.django_db
def test_waste_entry_daylock(admin_user, worker, item, client):
    today = date.today()
    sec1 = Section.objects.create(name="Mixing", code="MIX")
    l1 = DailyLedger.objects.create(date=today, section=sec1, item=item, opening_balance=Decimal("10.00"), waste_qty=Decimal("0.00"))
    DayLock.objects.create(section=sec1, lock_date=today, is_locked=True)

    client.force_login(admin_user)
    resp = client.post(reverse("production:waste-entry"), data={
        "date": today.isoformat(),
        "section": sec1.id,
        "form-TOTAL_FORMS": "1",
        "form-INITIAL_FORMS": "1",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
        "form-0-id": l1.id,
        "form-0-waste_qty": "2.50",
    })

    # Form should fail validation due to DayLock
    assert resp.status_code == 200
    assert len(resp.context["formset"].errors) > 0
    assert "is locked for" in str(resp.context["formset"].errors[0])

    # Assert waste not changed
    l1.refresh_from_db()
    assert l1.waste_qty == Decimal("0.00")
