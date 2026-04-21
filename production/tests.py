from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.contrib.admin.sites import AdminSite
from django.urls import reverse

from .admin import ProductionEntryAdmin
from .models import AttendanceLine, AttendanceSheet, AuditEvent, DailyLedger, DayLock, Item, Machine, MachineDowntime, ProcessFlowEdge, ProductionEntry, Section, TargetRule, WasteEntry, Worker

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
    assert response.context["rows"][0]["waste_percentage"] == Decimal("10.00")


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


class MachineDowntimeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="supervisor", password="pw")
        self.section = Section.objects.create(name="Packing", code="PCK")
        self.section.supervisors.add(self.user)
        self.machine = Machine.objects.create(section=self.section, name="Packer 1", machine_code="P1")
        self.machine2 = Machine.objects.create(section=self.section, name="Packer 2", machine_code="P2")
        self.today = date.today()

    def test_downtime_duration_calculation(self):
        dt = MachineDowntime(
            machine=self.machine,
            downtime_date=self.today,
            start_time=time(10, 0),
            end_time=time(11, 30),
            logged_by=self.user,
        )
        dt.save()
        self.assertEqual(dt.duration_minutes, 90)

    def test_downtime_overlap_prevention(self):
        MachineDowntime.objects.create(
            machine=self.machine,
            downtime_date=self.today,
            start_time=time(10, 0),
            end_time=time(12, 0),
            logged_by=self.user,
        )

        # Overlapping start time
        with self.assertRaises(ValidationError):
            dt = MachineDowntime(
                machine=self.machine,
                downtime_date=self.today,
                start_time=time(11, 0),
                end_time=time(13, 0),
                logged_by=self.user,
            )
            dt.clean()

        # Enveloping
        with self.assertRaises(ValidationError):
            dt = MachineDowntime(
                machine=self.machine,
                downtime_date=self.today,
                start_time=time(9, 0),
                end_time=time(13, 0),
                logged_by=self.user,
            )
            dt.clean()

        # No overlap (before)
        dt_before = MachineDowntime(
            machine=self.machine,
            downtime_date=self.today,
            start_time=time(8, 0),
            end_time=time(9, 0),
            logged_by=self.user,
        )
        dt_before.clean()  # Should not raise

        # No overlap (different machine)
        dt_other_machine = MachineDowntime(
            machine=self.machine2,
            downtime_date=self.today,
            start_time=time(10, 0),
            end_time=time(12, 0),
            logged_by=self.user,
        )
        dt_other_machine.clean()  # Should not raise

    def test_daylock_blocks_downtime(self):
        DayLock.objects.create(section=self.section, lock_date=self.today, is_locked=True)

        with self.assertRaises(ValidationError) as cm:
            dt = MachineDowntime(
                machine=self.machine,
                downtime_date=self.today,
                start_time=time(10, 0),
                end_time=time(12, 0),
                logged_by=self.user,
            )
            dt.clean()
        self.assertIn("locked", str(cm.exception))

    def test_backdated_downtime_prevented(self):
        past_date = date.today() - timedelta(days=1)
        with self.assertRaises(ValidationError) as cm:
            dt = MachineDowntime(
                machine=self.machine,
                downtime_date=past_date,
                start_time=time(10, 0),
                end_time=time(12, 0),
                logged_by=self.user,
            )
            dt.clean()
        self.assertIn("backdated", str(cm.exception))

class DowntimeViewsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="supervisor", password="pw")
        self.section = Section.objects.create(name="Packing", code="PCK")
        self.section.supervisors.add(self.user)
        self.machine = Machine.objects.create(section=self.section, name="Packer 1", machine_code="P1")
        self.user.groups.add(Group.objects.get_or_create(name="SUPERVISOR")[0])
        self.client.login(username="supervisor", password="pw")
        self.today = date.today()

    def test_downtime_entry_view_get(self):
        response = self.client.get(reverse("production:downtime-entry"))
        self.assertEqual(response.status_code, 200)

    def test_downtime_entry_view_post(self):
        data = {
            "downtime_date": self.today.isoformat(),
            "machine": self.machine.id,
            "start_time": "10:00",
            "end_time": "11:30",
            "reason": "Jammed",
        }
        response = self.client.post(reverse("production:downtime-entry"), data)
        self.assertEqual(response.status_code, 302)  # Redirects to list
        self.assertEqual(MachineDowntime.objects.count(), 1)
        dt = MachineDowntime.objects.first()
        self.assertEqual(dt.duration_minutes, 90)

    def test_downtime_list_view(self):
        MachineDowntime.objects.create(
            machine=self.machine,
            downtime_date=self.today,
            start_time=time(10, 0),
            end_time=time(11, 30),
            logged_by=self.user,
        )
        response = self.client.get(reverse("production:downtime-list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Packer 1", response.content)
