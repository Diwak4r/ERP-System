from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.contrib.admin.sites import AdminSite
from django.urls import reverse

from .admin import ProductionEntryAdmin
from .models import (
    AttendanceLine,
    AttendanceSheet,
    AuditEvent,
    DailyLedger,
    DayLock,
    Item,
    Machine,
    MachineDowntime,
    ProcessFlowEdge,
    ProductionEntry,
    Requisition,
    Section,
    StatusHistory,
    TargetRule,
    WasteEntry,
    Worker,
)

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
def store_user(db):
    User = get_user_model()
    user = User.objects.create_user(username="store-user", password="pass")
    group, _ = Group.objects.get_or_create(name="STORE")
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


@pytest.fixture
def machine(section):
    return Machine.objects.create(section=section, name="Machine A", machine_code="MCH-001")


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


def test_waste_entry_updates_ledger(admin_user, section, item, client):
    today = date.today()
    DailyLedger.objects.create(
        date=today,
        section=section,
        item=item,
        opening_balance=Decimal("100.00"),
    )
    client.force_login(admin_user)
    response = client.post(
        reverse("production:waste-entry"),
        data={
            "waste_date": today.isoformat(),
            "section": section.id,
            "waste-TOTAL_FORMS": "1",
            "waste-INITIAL_FORMS": "0",
            "waste-MIN_NUM_FORMS": "0",
            "waste-MAX_NUM_FORMS": "1000",
            "waste-0-item": item.id,
            "waste-0-waste_qty": "12.50",
            "waste-0-reason": "Damaged batch",
        },
        follow=True,
    )
    assert response.status_code == 200
    assert WasteEntry.objects.count() == 1
    ledger = DailyLedger.objects.get(date=today, section=section, item=item)
    assert ledger.waste_qty == Decimal("12.50")


def test_waste_entry_permission_enforced(supervisor_user, item, client):
    my_section = Section.objects.create(name="Cutting", code="CUT")
    my_section.supervisors.add(supervisor_user)
    other_section = Section.objects.create(name="Packing", code="PCK")
    DailyLedger.objects.create(date=date.today(), section=other_section, item=item, opening_balance=Decimal("50.00"))

    client.force_login(supervisor_user)
    response = client.post(
        reverse("production:waste-entry"),
        data={
            "waste_date": date.today().isoformat(),
            "section": other_section.id,
            "waste-TOTAL_FORMS": "1",
            "waste-INITIAL_FORMS": "0",
            "waste-MIN_NUM_FORMS": "0",
            "waste-MAX_NUM_FORMS": "1000",
            "waste-0-item": item.id,
            "waste-0-waste_qty": "1.00",
            "waste-0-reason": "Rejected",
        },
    )
    assert response.status_code == 403
    assert WasteEntry.objects.count() == 0


def test_waste_entry_daylock_prevents_save(admin_user, section, item, client):
    today = date.today()
    DayLock.objects.create(section=section, lock_date=today, is_locked=True)
    DailyLedger.objects.create(date=today, section=section, item=item, opening_balance=Decimal("20.00"))
    client.force_login(admin_user)
    response = client.post(
        reverse("production:waste-entry"),
        data={
            "waste_date": today.isoformat(),
            "section": section.id,
            "waste-TOTAL_FORMS": "1",
            "waste-INITIAL_FORMS": "0",
            "waste-MIN_NUM_FORMS": "0",
            "waste-MAX_NUM_FORMS": "1000",
            "waste-0-item": item.id,
            "waste-0-waste_qty": "2.00",
            "waste-0-reason": "Lock test",
        },
    )
    assert response.status_code == 200
    assert WasteEntry.objects.count() == 0
    assert b"is locked" in response.content


def test_wastage_report_shows_percentage(admin_user, section, item, client):
    ledger = DailyLedger.objects.create(
        date=date.today(),
        section=section,
        item=item,
        opening_balance=Decimal("80.00"),
        received_from_prev=Decimal("20.00"),
    )
    WasteEntry.objects.create(
        waste_date=ledger.date,
        section=section,
        item=item,
        waste_qty=Decimal("10.00"),
        reason="Cutoff waste",
        created_by=admin_user,
    )

    client.force_login(admin_user)
    response = client.get(reverse("production:report-wastage"))
    assert response.status_code == 200
    assert response.context["page_obj"][0]["waste_percentage"] == Decimal("10.00")


def test_attendance_entry_saves_present_workers(supervisor_user, section, worker, client):
    worker_2 = Worker.objects.create(name="Jane", employee_code="W002")

    client.force_login(supervisor_user)
    response = client.post(
        reverse("production:attendance-entry"),
        data={
            "attendance_date": date.today().isoformat(),
            "section": section.id,
            "workers": [worker.id, worker_2.id],
        },
        follow=True,
    )

    assert response.status_code == 200
    sheet = AttendanceSheet.objects.get(attendance_date=date.today(), section=section)
    assert sheet.created_by == supervisor_user
    assert AttendanceLine.objects.filter(sheet=sheet).count() == 2


def test_attendance_entry_permission_enforced(supervisor_user, worker, client):
    my_section = Section.objects.create(name="Cutting Attendance", code="CUT-AT")
    my_section.supervisors.add(supervisor_user)
    other_section = Section.objects.create(name="Packing Attendance", code="PCK-AT")

    client.force_login(supervisor_user)
    response = client.post(
        reverse("production:attendance-entry"),
        data={
            "attendance_date": date.today().isoformat(),
            "section": other_section.id,
            "workers": [worker.id],
        },
    )

    assert response.status_code == 403
    assert AttendanceSheet.objects.count() == 0


def test_attendance_entry_daylock_prevents_save(admin_user, section, worker, client):
    today = date.today()
    DayLock.objects.create(section=section, lock_date=today, is_locked=True)

    client.force_login(admin_user)
    response = client.post(
        reverse("production:attendance-entry"),
        data={
            "attendance_date": today.isoformat(),
            "section": section.id,
            "workers": [worker.id],
        },
    )

    assert response.status_code == 200
    assert AttendanceSheet.objects.count() == 0
    assert b"is locked" in response.content


def test_attendance_sheet_backdate_validation(admin_user, section):
    sheet = AttendanceSheet(
        attendance_date=date.today() - timedelta(days=1),
        section=section,
        created_by=admin_user,
    )
    with pytest.raises(ValidationError, match="Cannot create backdated attendance sheets."):
        sheet.clean()


def test_attendance_report_shows_daily_and_trend_data(admin_user, section, worker, client):
    worker_2 = Worker.objects.create(name="Ajay", employee_code="W003")
    sheet = AttendanceSheet.objects.create(
        attendance_date=date.today(),
        section=section,
        created_by=admin_user,
    )
    AttendanceLine.objects.create(sheet=sheet, worker=worker, status=AttendanceLine.STATUS_PRESENT)
    AttendanceLine.objects.create(sheet=sheet, worker=worker_2, status=AttendanceLine.STATUS_PRESENT)

    client.force_login(admin_user)
    response = client.get(reverse("production:report-attendance"), {"date": date.today().isoformat(), "section": section.id})

    assert response.status_code == 200
    assert response.context["daily_rows"][0]["present_count"] == 2
    assert list(response.context["trend_rows"])[0]["present_count"] == 2


def test_machine_downtime_duration_calculation(supervisor_user, machine):
    entry = MachineDowntime(
        machine=machine,
        downtime_date=date.today(),
        start_time=time(hour=9, minute=0),
        end_time=time(hour=11, minute=30),
        reason="Maintenance",
        logged_by=supervisor_user,
    )
    entry.full_clean()
    entry.save()
    assert entry.duration_minutes == 150


def test_machine_downtime_overlap_prevention(supervisor_user, machine):
    MachineDowntime.objects.create(
        machine=machine,
        downtime_date=date.today(),
        start_time=time(hour=9, minute=0),
        end_time=time(hour=10, minute=0),
        reason="Power cut",
        logged_by=supervisor_user,
    )

    overlapping = MachineDowntime(
        machine=machine,
        downtime_date=date.today(),
        start_time=time(hour=9, minute=30),
        end_time=time(hour=10, minute=30),
        reason="Belt issue",
        logged_by=supervisor_user,
    )
    with pytest.raises(ValidationError, match="overlaps an existing entry"):
        overlapping.full_clean()


def test_machine_downtime_daylock_block(supervisor_user, section, machine, client):
    today = date.today()
    DayLock.objects.create(section=section, lock_date=today, is_locked=True)
    client.force_login(supervisor_user)

    response = client.post(
        reverse("production:downtime-entry"),
        data={
            "section": section.id,
            "machine": machine.id,
            "downtime_date": today.isoformat(),
            "start_time": "10:00",
            "end_time": "11:00",
            "reason": "Locked day test",
        },
    )

    assert response.status_code == 200
    assert MachineDowntime.objects.count() == 0
    assert b"is locked" in response.content


def test_machine_downtime_rbac(supervisor_user, section, machine, client):
    other_section = Section.objects.create(name="Mixing", code="MIX")
    other_machine = Machine.objects.create(section=other_section, name="Machine B", machine_code="MCH-002")
    client.force_login(supervisor_user)

    blocked = client.post(
        reverse("production:downtime-entry"),
        data={
            "section": other_section.id,
            "machine": other_machine.id,
            "downtime_date": date.today().isoformat(),
            "start_time": "12:00",
            "end_time": "13:00",
            "reason": "Unauthorized section",
        },
    )
    assert blocked.status_code == 403

    allowed = client.post(
        reverse("production:downtime-entry"),
        data={
            "section": section.id,
            "machine": machine.id,
            "downtime_date": date.today().isoformat(),
            "start_time": "13:00",
            "end_time": "14:00",
            "reason": "Authorized section",
        },
        follow=True,
    )
    assert allowed.status_code == 200
    assert MachineDowntime.objects.count() == 1


def test_downtime_list_and_dashboard_alert(admin_user, section, machine, client):
    MachineDowntime.objects.create(
        machine=machine,
        downtime_date=date.today(),
        start_time=time(hour=8, minute=0),
        end_time=time(hour=9, minute=0),
        reason="Calibration",
        logged_by=admin_user,
    )

    client.force_login(admin_user)
    report_response = client.get(reverse("production:downtime-list"), {"date": date.today().isoformat()})
    assert report_response.status_code == 200
    assert b"Machine Downtime Report" in report_response.content
    assert b"Machine A" in report_response.content

    dashboard_response = client.get(reverse("production:report-daily-section"), {"date": date.today().isoformat()})
    assert dashboard_response.status_code == 200
    assert b"Machine Downtime Alerts (Today)" in dashboard_response.content


def test_requisition_create_rbac_and_store_submission(supervisor_user, store_user, section, item, client):
    section.supervisors.add(store_user)

    client.force_login(supervisor_user)
    blocked = client.post(
        reverse("production:requisition-create"),
        data={"item": item.id, "requested_qty": "10.50", "note": "Need raw material"},
    )
    assert blocked.status_code == 403

    client.force_login(store_user)
    allowed = client.post(
        reverse("production:requisition-create"),
        data={"item": item.id, "requested_qty": "10.50", "note": "Need raw material"},
        follow=True,
    )
    assert allowed.status_code == 200
    req = Requisition.objects.get()
    assert req.status == Requisition.STATUS_PENDING
    assert req.requested_by == store_user
    assert req.requested_section == section
    assert StatusHistory.objects.filter(requisition=req, to_status=Requisition.STATUS_PENDING).exists()


def test_requisition_list_scope_for_store_vs_admin(admin_user, store_user, section, item, client):
    section.supervisors.add(store_user)
    own = Requisition.objects.create(
        item=item,
        requested_qty=Decimal("8.00"),
        note="Own req",
        requested_by=store_user,
        requested_section=section,
    )
    other_store = get_user_model().objects.create_user(username="store-other", password="pass")
    store_group = Group.objects.get(name="STORE")
    other_store.groups.add(store_group)
    section.supervisors.add(other_store)
    Requisition.objects.create(
        item=item,
        requested_qty=Decimal("12.00"),
        note="Other req",
        requested_by=other_store,
        requested_section=section,
    )

    client.force_login(store_user)
    store_response = client.get(reverse("production:requisition-list"))
    assert store_response.status_code == 200
    requisitions = list(store_response.context["page_obj"])
    assert requisitions == [own]

    client.force_login(admin_user)
    admin_response = client.get(reverse("production:requisition-list"))
    assert admin_response.status_code == 200
    assert admin_response.context["pending_requisition_count"] == 2
    assert admin_response.context["is_admin"] is True


def test_requisition_approval_updates_ledger_and_locks_transition(admin_user, store_user, section, item, client):
    section.supervisors.add(store_user)
    requisition = Requisition.objects.create(
        item=item,
        requested_qty=Decimal("25.00"),
        note="Need stock",
        requested_by=store_user,
        requested_section=section,
    )

    client.force_login(admin_user)
    approve = client.post(
        reverse("production:requisition-detail", args=[requisition.id]),
        data={"decision": Requisition.STATUS_APPROVED, "note": "Approved"},
        follow=True,
    )
    assert approve.status_code == 200
    requisition.refresh_from_db()
    assert requisition.status == Requisition.STATUS_APPROVED
    assert requisition.reviewed_by == admin_user
    assert requisition.reviewed_at is not None
    assert StatusHistory.objects.filter(
        requisition=requisition,
        from_status=Requisition.STATUS_PENDING,
        to_status=Requisition.STATUS_APPROVED,
    ).exists()

    ledger = DailyLedger.objects.get(
        date=requisition.requested_date,
        section=section,
        item=item,
    )
    assert ledger.manual_received == Decimal("25.00")

    second_review = client.post(
        reverse("production:requisition-detail", args=[requisition.id]),
        data={"decision": Requisition.STATUS_REJECTED, "note": "late reject"},
        follow=True,
    )
    assert second_review.status_code == 200
    requisition.refresh_from_db()
    assert requisition.status == Requisition.STATUS_APPROVED
    assert StatusHistory.objects.filter(requisition=requisition, to_status=Requisition.STATUS_REJECTED).count() == 0


def test_requisition_rejection_requires_reason(admin_user, store_user, section, item, client):
    section.supervisors.add(store_user)
    requisition = Requisition.objects.create(
        item=item,
        requested_qty=Decimal("5.00"),
        note="",
        requested_by=store_user,
        requested_section=section,
    )

    client.force_login(admin_user)
    response = client.post(
        reverse("production:requisition-detail", args=[requisition.id]),
        data={"decision": Requisition.STATUS_REJECTED, "note": ""},
    )
    assert response.status_code == 200
    requisition.refresh_from_db()
    assert requisition.status == Requisition.STATUS_PENDING
    assert b"Rejection reason is required" in response.content


def test_dashboard_shows_pending_requisition_badge(admin_user, store_user, section, item, worker, client):
    section.supervisors.add(store_user)
    Requisition.objects.create(
        item=item,
        requested_qty=Decimal("3.00"),
        note="one",
        requested_by=store_user,
        requested_section=section,
    )
    Requisition.objects.create(
        item=item,
        requested_qty=Decimal("4.00"),
        note="two",
        requested_by=store_user,
        requested_section=section,
    )
    ProductionEntry.objects.create(
        entry_date=date.today(),
        section=section,
        worker=worker,
        item=item,
        target_qty=Decimal("10"),
        actual_qty=Decimal("10"),
        shift_hours=Decimal("8"),
        created_by=admin_user,
    )

    client.force_login(admin_user)
    response = client.get(reverse("production:report-daily-section"), {"date": date.today().isoformat()})
    assert response.status_code == 200
    assert response.context["pending_requisition_count"] == 2
    assert b"pending-requisition-badge" in response.content


def test_csv_import_export_page_requires_admin(supervisor_user, client):
    unauthenticated = client.get(reverse("production:csv-import-export"))
    assert unauthenticated.status_code == 302

    client.force_login(supervisor_user)
    forbidden = client.get(reverse("production:csv-import-export"))
    assert forbidden.status_code == 403


def test_csv_template_requires_admin(supervisor_user, client):
    client.force_login(supervisor_user)
    response = client.get(reverse("production:csv-template", kwargs={"model_name": "item"}))
    assert response.status_code == 403


def test_csv_template_generation(admin_user, client):
    client.force_login(admin_user)
    response = client.get(reverse("production:csv-template", kwargs={"model_name": "worker"}))
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert response.content.decode("utf-8").strip() == "name,employee_code,is_daily_wage,is_active"


def test_csv_export_headers_content_and_formula_safety(admin_user, client):
    Item.objects.create(name="=Danger", sku="ITEM-CSV-001", unit=Item.UNIT_KG, is_active=True)

    client.force_login(admin_user)
    response = client.get(reverse("production:csv-export", kwargs={"model_name": "item"}))

    assert response.status_code == 200
    content_lines = response.content.decode("utf-8").splitlines()
    assert content_lines[0] == "name,sku,unit,is_active"
    assert content_lines[1] == "'=Danger,ITEM-CSV-001,KG,True"


def test_csv_import_item_success(admin_user, client):
    client.force_login(admin_user)
    csv_content = b"name,sku,unit,is_active\nNew Item,NEW-001,PCS,true"
    csv_file = SimpleUploadedFile("items.csv", csv_content, content_type="text/csv")

    response = client.post(
        reverse("production:csv-import-export"),
        data={"model_name": "item", "csv_file": csv_file},
        follow=True,
    )

    assert response.status_code == 200
    assert Item.objects.filter(sku="NEW-001", name="New Item", unit=Item.UNIT_PCS).exists()


def test_csv_import_rollback_with_row_level_errors(admin_user, client):
    client.force_login(admin_user)
    csv_content = b"name,sku,unit,is_active\nGood Item,GOOD-001,PCS,true\nBad Bool,BAD-001,PCS,not-bool"
    csv_file = SimpleUploadedFile("items.csv", csv_content, content_type="text/csv")

    response = client.post(
        reverse("production:csv-import-export"),
        data={"model_name": "item", "csv_file": csv_file},
        follow=True,
    )

    assert response.status_code == 200
    assert not Item.objects.filter(sku="GOOD-001").exists()
    messages = [str(message) for message in response.context["messages"]]
    assert any("Row 3:" in message for message in messages)
    assert any("is_active" in message for message in messages)


def test_csv_import_machine_section_code_mapping(admin_user, section, client):
    client.force_login(admin_user)
    csv_content = f"section_code,name,machine_code,is_active\n{section.code},Machine CSV,CSV-M-01,true".encode()
    csv_file = SimpleUploadedFile("machines.csv", csv_content, content_type="text/csv")

    response = client.post(
        reverse("production:csv-import-export"),
        data={"model_name": "machine", "csv_file": csv_file},
        follow=True,
    )

    assert response.status_code == 200
    machine = Machine.objects.get(machine_code="CSV-M-01")
    assert machine.section == section


def test_csv_import_requires_known_section_code(admin_user, client):
    client.force_login(admin_user)
    csv_content = b"section_code,name,machine_code,is_active\nUNKNOWN,Machine CSV,CSV-M-02,true"
    csv_file = SimpleUploadedFile("machines.csv", csv_content, content_type="text/csv")

    response = client.post(
        reverse("production:csv-import-export"),
        data={"model_name": "machine", "csv_file": csv_file},
        follow=True,
    )

    assert response.status_code == 200
    assert not Machine.objects.filter(machine_code="CSV-M-02").exists()
    messages = [str(message) for message in response.context["messages"]]
    assert any("Row 2:" in message and "Section with code 'UNKNOWN' not found." in message for message in messages)

def test_pagination_logic_for_requisition_list(admin_user, section, item, client):
    """Verify that pagination limits items to 50 per page."""
    # Create 51 requisitions
    reqs = [
        Requisition(
            item=item,
            requested_qty=Decimal("1.00"),
            note=f"Req {i}",
            requested_by=admin_user,
            requested_section=section,
        )
        for i in range(51)
    ]
    Requisition.objects.bulk_create(reqs)

    client.force_login(admin_user)

    # Page 1 should have 50 items
    response = client.get(reverse("production:requisition-list"))
    assert response.status_code == 200
    page_obj = response.context["page_obj"]
    assert len(page_obj.object_list) == 50
    assert page_obj.paginator.num_pages == 2

    # Page 2 should have 1 item
    response_p2 = client.get(reverse("production:requisition-list"), {"page": 2})
    assert response_p2.status_code == 200
    page_obj_p2 = response_p2.context["page_obj"]
    assert len(page_obj_p2.object_list) == 1
