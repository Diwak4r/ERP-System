from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, F, ExpressionWrapper, FloatField, Case, When, Value, BooleanField, Count, Q
from django.db.models.functions import Cast

from .forms import (
    AttendanceEntryForm,
    MachineDowntimeForm,
    ProductionEntryForm,
    ProductionEntryFormSet,
    RequisitionDecisionForm,
    RequisitionForm,
    WasteEntryForm,
    WasteEntryFormSet,
)
from .models import (
    AttendanceLine,
    AttendanceSheet,
    DailyLedger,
    Item,
    MachineDowntime,
    ProductionEntry,
    Requisition,
    Section,
    StatusHistory,
    TargetRule,
    WasteEntry,
    Worker,
)

ROLE_ADMIN = "ADMIN"
ROLE_SUPERVISOR = "SUPERVISOR"
ROLE_STORE = "STORE"


def _user_has_role(user, role: str) -> bool:
    return user.is_superuser or user.groups.filter(name=role).exists()


def _available_sections(user):
    if _user_has_role(user, ROLE_ADMIN):
        return Section.objects.filter(is_active=True)
    return Section.objects.filter(is_active=True, supervisors=user)


def _ensure_permission(user, section: Section) -> bool:
    if _user_has_role(user, ROLE_ADMIN):
        return True
    return _user_has_role(user, ROLE_SUPERVISOR) and section.supervisors.filter(id=user.id).exists()


def _target_for(section: Section, item: Item, entry_date: date):
    return TargetRule.objects.for_section_item_date(section=section, item=item, target_date=entry_date).first()


def _coerce_date(raw_value: str | None, default_value: date) -> date:
    try:
        return date.fromisoformat(raw_value) if raw_value else default_value
    except ValueError:
        return default_value


def _pending_requisition_count(user) -> int:
    if not _user_has_role(user, ROLE_ADMIN):
        return 0
    return Requisition.objects.filter(status=Requisition.STATUS_PENDING).count()


def _store_section_for(user) -> Section | None:
    sections = Section.objects.filter(is_active=True, supervisors=user)
    if sections.count() == 1:
        return sections.first()
    return None


@login_required
def production_entry(request: HttpRequest) -> HttpResponse:
    today = date.today()
    entry_date_str = request.POST.get("entry_date") or request.GET.get("entry_date")
    entry_date_val = date.fromisoformat(entry_date_str) if entry_date_str else today

    sections = _available_sections(request.user)
    selected_section_id = request.POST.get("section") or request.GET.get("section") or (sections.first().id if sections else None)
    selected_section = Section.objects.filter(id=selected_section_id).first() if selected_section_id else None

    if selected_section and not _ensure_permission(request.user, selected_section):
        return HttpResponseForbidden("You are not allowed to create entries for this section")

    form_kwargs = {"section": selected_section, "entry_date": entry_date_val}

    if request.method == "POST":
        formset = ProductionEntryFormSet(request.POST, prefix="form", form_kwargs=form_kwargs)
        if not selected_section:
            messages.error(request, "Section is required")
        if formset.is_valid() and selected_section:
            created_entries = []
            for form in formset:
                data = form.cleaned_data
                entry = ProductionEntry(
                    entry_date=entry_date_val,
                    section=selected_section,
                    worker=data["worker"],
                    item=data["item"],
                    target_qty=Decimal(data.get("target_qty") or 0),
                    actual_qty=Decimal(data.get("actual_qty") or 0),
                    shift_hours=Decimal(data.get("shift_hours") or 0),
                    created_by=request.user,
                )
                entry.set_outcomes()
                entry.save()
                created_entries.append(entry)
                if entry.target_qty <= 0:
                    messages.warning(request, f"No target rule found for {entry.item}; overtime set to 0")
            messages.success(request, f"Saved {len(created_entries)} production entr{'y' if len(created_entries)==1 else 'ies'}")
            return redirect("production:entries")
    else:
        formset = ProductionEntryFormSet(prefix="form", initial=[{}], form_kwargs=form_kwargs)

    context = {
        "formset": formset,
        "entry_date": entry_date_val,
        "sections": sections,
        "selected_section": selected_section,
    }
    return render(request, "production/entry_form.html", context)


@login_required
def production_entry_row(request: HttpRequest) -> HttpResponse:
    section_id = request.GET.get("section")
    entry_date_str = request.GET.get("entry_date")
    form_count = int(request.GET.get("form_count", 0))
    section = get_object_or_404(Section, id=section_id) if section_id else None
    if section and not _ensure_permission(request.user, section):
        return HttpResponseForbidden("Not allowed")
    try:
        entry_date_val = date.fromisoformat(entry_date_str) if entry_date_str else date.today()
    except ValueError:
        entry_date_val = date.today()
    form = ProductionEntryForm(prefix=f"form-{form_count}", section=section, entry_date=entry_date_val)
    html = render_to_string(
        "production/entry_row.html",
        {"form": form, "index": form_count, "next_index": form_count + 1},
        request=request,
    )
    return HttpResponse(html)


@login_required
def production_entries(request: HttpRequest) -> HttpResponse:
    sections = _available_sections(request.user)
    entry_date_str = request.GET.get("date")
    section_id = request.GET.get("section")
    try:
        entry_date_val = date.fromisoformat(entry_date_str) if entry_date_str else date.today()
    except ValueError:
        entry_date_val = date.today()
    selected_section = Section.objects.filter(id=section_id).first() if section_id else None
    if selected_section and not _ensure_permission(request.user, selected_section):
        return HttpResponseForbidden("Not allowed")
    entries = ProductionEntry.objects.select_related("worker", "item", "section").filter(entry_date=entry_date_val)
    if selected_section:
        entries = entries.filter(section=selected_section)
    entries = entries.order_by("section__name", "worker__name")
    context = {
        "entries": entries,
        "entry_date": entry_date_val,
        "sections": sections,
        "selected_section": selected_section,
    }
    return render(request, "production/entries_list.html", context)


@login_required
def daily_section_summary(request: HttpRequest) -> HttpResponse:
    sections = _available_sections(request.user)
    entry_date_str = request.GET.get("date")
    section_id = request.GET.get("section")

    try:
        entry_date_val = date.fromisoformat(entry_date_str) if entry_date_str else date.today()
    except ValueError:
        entry_date_val = date.today()
    selected_section = Section.objects.filter(id=section_id).first() if section_id else (sections.first() if sections else None)

    if selected_section and not _ensure_permission(request.user, selected_section):
        return HttpResponseForbidden("Not allowed")

    entries = ProductionEntry.objects.filter(entry_date=entry_date_val)
    if selected_section:
        entries = entries.filter(section=selected_section)

    # Aggregate per item
    item_summary = entries.values('item__name').annotate(
        total_actual=Sum('actual_qty'),
        total_target=Sum('target_qty')
    ).order_by('item__name')

    # Aggregate per worker
    worker_summary = entries.values('worker__id', 'worker__name', 'worker__employee_code').annotate(
            total_actual=Sum('actual_qty'),
            total_target=Sum('target_qty'),
        ).annotate(
            target_hit=Case(
                When(total_actual__gte=F('total_target'), then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            )
        ).order_by('worker__name')

    worker_count = entries.values('worker').distinct().count()
    today = date.today()
    downtime_alert_qs = (
        MachineDowntime.objects.filter(downtime_date=today, machine__section__in=sections)
        .select_related("machine", "machine__section")
    )
    if selected_section:
        downtime_alert_qs = downtime_alert_qs.filter(machine__section=selected_section)

    downtime_alerts = (
        downtime_alert_qs.values("machine__name", "machine__machine_code", "machine__section__name")
        .annotate(total_minutes=Sum("duration_minutes"))
        .order_by("machine__section__name", "machine__name")
    )

    context = {
        "sections": sections,
        "selected_section": selected_section,
        "entry_date": entry_date_val,
        "item_summary": item_summary,
        "worker_summary": worker_summary,
        "worker_count": worker_count,
        "today_downtime_alerts": downtime_alerts,
        "is_today_view": entry_date_val == today,
        "pending_requisition_count": _pending_requisition_count(request.user),
        "is_admin": _user_has_role(request.user, ROLE_ADMIN),
    }
    return render(request, "production/reports/daily_section_summary.html", context)

@login_required
def item_aggregate(request: HttpRequest) -> HttpResponse:
    sections = _available_sections(request.user)
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")

    try:
        start_date_val = date.fromisoformat(start_date_str) if start_date_str else date.today().replace(day=1)
    except ValueError:
        start_date_val = date.today().replace(day=1)

    try:
        end_date_val = date.fromisoformat(end_date_str) if end_date_str else date.today()
    except ValueError:
        end_date_val = date.today()

    entries = ProductionEntry.objects.filter(
        entry_date__gte=start_date_val,
        entry_date__lte=end_date_val,
        section__in=sections
    )

    item_summary = entries.values('item__name', 'item__unit').annotate(
        total_actual=Sum('actual_qty'),
        total_target=Sum('target_qty'),
    ).annotate(
        hit_rate=Case(
            When(total_target__gt=0, then=ExpressionWrapper(
                Cast('total_actual', FloatField()) / Cast('total_target', FloatField()) * 100.0,
                output_field=FloatField()
            )),
            default=Value(0.0),
            output_field=FloatField()
        )
    ).order_by('item__name')

    context = {
        "start_date": start_date_val,
        "end_date": end_date_val,
        "item_summary": item_summary,
    }
    return render(request, "production/reports/item_aggregate.html", context)

@login_required
def worker_history(request: HttpRequest, worker_id: int) -> HttpResponse:
    worker = get_object_or_404(Worker, id=worker_id)
    sections = _available_sections(request.user)

    entries = ProductionEntry.objects.filter(
        worker=worker,
        section__in=sections
    ).select_related('item', 'section').order_by('-entry_date')[:30] # Last 30 entries

    context = {
        "worker": worker,
        "entries": entries,
    }
    return render(request, "production/reports/worker_history_modal.html", context)


@login_required
def requisition_create(request: HttpRequest) -> HttpResponse:
    if not _user_has_role(request.user, ROLE_STORE):
        return HttpResponseForbidden("Only STORE users can create requisitions")

    store_section = _store_section_for(request.user)
    if store_section is None:
        return HttpResponseForbidden("STORE user must be assigned to exactly one active section")

    if request.method == "POST":
        form = RequisitionForm(request.POST)
        if form.is_valid():
            requisition = form.save(commit=False)
            requisition.requested_by = request.user
            requisition.requested_section = store_section
            requisition.requested_date = date.today()
            requisition.status = Requisition.STATUS_PENDING
            requisition.save()
            StatusHistory.objects.create(
                requisition=requisition,
                from_status="",
                to_status=Requisition.STATUS_PENDING,
                changed_by=request.user,
                note=(requisition.note or "").strip(),
            )
            messages.success(request, "Requisition submitted for admin review.")
            return redirect("production:requisition-list")
    else:
        form = RequisitionForm()

    return render(
        request,
        "production/requisition_form.html",
        {
            "form": form,
            "store_section": store_section,
            "pending_requisition_count": _pending_requisition_count(request.user),
        },
    )


@login_required
def requisition_list(request: HttpRequest) -> HttpResponse:
    if _user_has_role(request.user, ROLE_ADMIN):
        requisitions = Requisition.objects.select_related(
            "item",
            "requested_by",
            "requested_section",
            "reviewed_by",
        ).all()
    elif _user_has_role(request.user, ROLE_STORE):
        requisitions = Requisition.objects.select_related(
            "item",
            "requested_by",
            "requested_section",
            "reviewed_by",
        ).filter(requested_by=request.user)
    else:
        return HttpResponseForbidden("Not allowed")

    paginator = Paginator(requisitions.order_by("-created_at"), 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "production/requisition_list.html",
        {
            "page_obj": page_obj,
            "pending_requisition_count": _pending_requisition_count(request.user),
            "is_admin": _user_has_role(request.user, ROLE_ADMIN),
        },
    )


@login_required
def requisition_detail(request: HttpRequest, requisition_id: int) -> HttpResponse:
    if not _user_has_role(request.user, ROLE_ADMIN):
        return HttpResponseForbidden("Only ADMIN users can review requisitions")

    requisition = get_object_or_404(
        Requisition.objects.select_related(
            "item",
            "requested_by",
            "requested_section",
            "reviewed_by",
        ),
        pk=requisition_id,
    )

    decision_form = RequisitionDecisionForm()
    if request.method == "POST":
        decision_form = RequisitionDecisionForm(request.POST)
        if decision_form.is_valid():
            decision = decision_form.cleaned_data["decision"]
            note = decision_form.cleaned_data["note"]
            with transaction.atomic():
                locked_requisition = Requisition.objects.select_for_update().get(pk=requisition.pk)
                if locked_requisition.status != Requisition.STATUS_PENDING:
                    messages.error(request, "Only pending requisitions can be reviewed.")
                    return redirect("production:requisition-detail", requisition_id=requisition.id)

                previous_status = locked_requisition.status
                locked_requisition.status = decision
                locked_requisition.reviewed_by = request.user
                locked_requisition.reviewed_at = timezone.now()
                locked_requisition.save(update_fields=["status", "reviewed_by", "reviewed_at"])

                StatusHistory.objects.create(
                    requisition=locked_requisition,
                    from_status=previous_status,
                    to_status=decision,
                    changed_by=request.user,
                    note=note,
                )

                if decision == Requisition.STATUS_APPROVED:
                    ledger, _ = DailyLedger.objects.select_for_update().get_or_create(
                        date=locked_requisition.requested_date,
                        section=locked_requisition.requested_section,
                        item=locked_requisition.item,
                    )
                    ledger.manual_received = (ledger.manual_received or Decimal("0.00")) + locked_requisition.requested_qty
                    ledger.save(update_fields=["manual_received"])
                    messages.success(request, "Requisition approved and ledger updated.")
                else:
                    messages.success(request, "Requisition rejected.")

            return redirect("production:requisition-detail", requisition_id=requisition.id)

    requisition.refresh_from_db()
    history = requisition.status_history.select_related("changed_by").all()
    return render(
        request,
        "production/requisition_detail.html",
        {
            "requisition": requisition,
            "history": history,
            "decision_form": decision_form,
            "pending_requisition_count": _pending_requisition_count(request.user),
        },
    )


@login_required
def requisition_pending_badge(request: HttpRequest) -> HttpResponse:
    if not _user_has_role(request.user, ROLE_ADMIN):
        return HttpResponse("")
    return render(
        request,
        "production/requisition_pending_badge.html",
        {"pending_requisition_count": _pending_requisition_count(request.user)},
    )


@login_required
def requisition_notifications(request: HttpRequest) -> HttpResponse:
    if not _user_has_role(request.user, ROLE_ADMIN):
        return HttpResponse("")

    after_id_raw = request.GET.get("after_id", "0")
    try:
        after_id = max(int(after_id_raw), 0)
    except (TypeError, ValueError):
        after_id = 0

    new_requisitions = list(
        Requisition.objects.select_related("item", "requested_by", "requested_section")
        .filter(status=Requisition.STATUS_PENDING, id__gt=after_id)
        .order_by("id")[:5]
    )
    latest_pending_id = (
        Requisition.objects.filter(status=Requisition.STATUS_PENDING)
        .order_by("-id")
        .values_list("id", flat=True)
        .first()
        or after_id
    )

    return render(
        request,
        "production/requisition_notifications.html",
        {
            "new_requisitions": new_requisitions,
            "latest_pending_id": latest_pending_id,
        },
    )


@login_required
def attendance_entry(request: HttpRequest) -> HttpResponse:
    today = date.today()
    sections = _available_sections(request.user)
    initial_date = _coerce_date(request.POST.get("attendance_date") or request.GET.get("attendance_date"), today)
    selected_section_id = request.POST.get("section") or request.GET.get("section")

    initial = {
        "attendance_date": initial_date,
        "created_by": request.user,
    }
    if selected_section_id:
        initial["section"] = selected_section_id

    if request.method == "POST":
        form = AttendanceEntryForm(request.POST, sections=sections, initial=initial)
        section = form.data.get("section")
        selected_section = Section.objects.filter(id=section).first() if section else None
        if selected_section and not _ensure_permission(request.user, selected_section):
            return HttpResponseForbidden("You are not allowed to create attendance for this section")

        if form.is_valid():
            attendance_date = form.cleaned_data["attendance_date"]
            selected_section = form.cleaned_data["section"]
            selected_workers = list(form.cleaned_data["workers"])

            with transaction.atomic():
                sheet = AttendanceSheet.objects.filter(
                    attendance_date=attendance_date,
                    section=selected_section,
                ).first()
                if sheet is None:
                    sheet = AttendanceSheet(
                        attendance_date=attendance_date,
                        section=selected_section,
                        created_by=request.user,
                    )
                sheet.full_clean()
                if sheet.pk is None:
                    sheet.save()

                AttendanceLine.objects.filter(sheet=sheet).delete()
                AttendanceLine.objects.bulk_create(
                    [
                        AttendanceLine(sheet=sheet, worker=worker, status=AttendanceLine.STATUS_PRESENT)
                        for worker in selected_workers
                    ]
                )

            messages.success(request, f"Attendance saved for {len(selected_workers)} workers.")
            return redirect(f"{reverse('production:report-attendance')}?date={attendance_date.isoformat()}&section={selected_section.id}")
    else:
        selected_section = Section.objects.filter(id=selected_section_id).first() if selected_section_id else sections.first()
        if selected_section and not _ensure_permission(request.user, selected_section):
            return HttpResponseForbidden("You are not allowed to create attendance for this section")
        existing_sheet = (
            AttendanceSheet.objects.prefetch_related("lines")
            .filter(attendance_date=initial_date, section=selected_section)
            .first()
            if selected_section
            else None
        )
        initial["section"] = selected_section.id if selected_section else None
        initial["workers"] = (
            [line.worker_id for line in existing_sheet.lines.all()]
            if existing_sheet
            else []
        )
        form = AttendanceEntryForm(sections=sections, initial=initial)

    context = {
        "form": form,
    }
    return render(request, "production/attendance_entry_form.html", context)


@login_required
def attendance_report(request: HttpRequest) -> HttpResponse:
    today = date.today()
    sections = _available_sections(request.user)
    report_date = _coerce_date(request.GET.get("date"), today)
    section_id = request.GET.get("section")
    selected_section = Section.objects.filter(id=section_id).first() if section_id else None

    if selected_section and not _ensure_permission(request.user, selected_section):
        return HttpResponseForbidden("Not allowed")

    sheets = AttendanceSheet.objects.select_related("section").prefetch_related("lines__worker").filter(
        attendance_date=report_date,
        section__in=sections,
    )
    if selected_section:
        sheets = sheets.filter(section=selected_section)

    daily_rows = []
    for sheet in sheets.order_by("section__name"):
        workers = [line.worker for line in sheet.lines.all() if line.status == AttendanceLine.STATUS_PRESENT]
        daily_rows.append(
            {
                "sheet": sheet,
                "present_count": len(workers),
                "workers": workers,
            }
        )

    trend_start = report_date.replace(day=1)
    trend = (
        AttendanceSheet.objects.filter(
            attendance_date__gte=trend_start,
            attendance_date__lte=report_date,
            section__in=sections,
        )
        .annotate(
            present_count=Count(
                "lines",
                filter=Q(lines__status=AttendanceLine.STATUS_PRESENT),
                distinct=True,
            )
        )
    )
    if selected_section:
        trend = trend.filter(section=selected_section)

    trend_rows = trend.values("attendance_date", "section__name", "present_count").order_by("-attendance_date", "section__name")

    context = {
        "report_date": report_date,
        "sections": sections,
        "selected_section": selected_section,
        "daily_rows": daily_rows,
        "trend_rows": trend_rows,
    }
    return render(request, "production/reports/attendance_report.html", context)


@login_required
def waste_entry(request: HttpRequest) -> HttpResponse:
    today = date.today()
    waste_date_val = _coerce_date(request.POST.get("waste_date") or request.GET.get("waste_date"), today)

    sections = _available_sections(request.user)
    selected_section_id = request.POST.get("section") or request.GET.get("section") or (sections.first().id if sections else None)
    selected_section = Section.objects.filter(id=selected_section_id).first() if selected_section_id else None

    if selected_section and not _ensure_permission(request.user, selected_section):
        return HttpResponseForbidden("You are not allowed to create waste entries for this section")

    form_kwargs = {"section": selected_section, "waste_date": waste_date_val}
    if request.method == "POST":
        formset = WasteEntryFormSet(request.POST, prefix="waste", form_kwargs=form_kwargs)
        if formset.is_valid() and selected_section:
            created_entries = []
            for form in formset:
                data = form.cleaned_data
                entry = WasteEntry(
                    waste_date=waste_date_val,
                    section=selected_section,
                    item=data["item"],
                    waste_qty=Decimal(data["waste_qty"]),
                    reason=data.get("reason") or "",
                    created_by=request.user,
                )
                entry.save()
                created_entries.append(entry)
            messages.success(request, f"Saved {len(created_entries)} waste entr{'y' if len(created_entries)==1 else 'ies'}")
            return redirect("production:report-wastage")
    else:
        formset = WasteEntryFormSet(prefix="waste", initial=[{}], form_kwargs=form_kwargs)

    context = {
        "formset": formset,
        "waste_date": waste_date_val,
        "sections": sections,
        "selected_section": selected_section,
    }
    return render(request, "production/waste_entry_form.html", context)


@login_required
def waste_entry_row(request: HttpRequest) -> HttpResponse:
    section_id = request.GET.get("section")
    waste_date_str = request.GET.get("waste_date")
    form_count = int(request.GET.get("form_count", 0))
    section = get_object_or_404(Section, id=section_id) if section_id else None
    if section and not _ensure_permission(request.user, section):
        return HttpResponseForbidden("Not allowed")
    waste_date_val = _coerce_date(waste_date_str, date.today())
    form = WasteEntryForm(prefix=f"waste-{form_count}", section=section, waste_date=waste_date_val)
    html = render_to_string(
        "production/waste_entry_row.html",
        {"form": form, "index": form_count, "next_index": form_count + 1},
        request=request,
    )
    return HttpResponse(html)


@login_required
def wastage_report(request: HttpRequest) -> HttpResponse:
    today = date.today()
    sections = _available_sections(request.user)
    start_date_val = _coerce_date(request.GET.get("start_date"), today.replace(day=1))
    end_date_val = _coerce_date(request.GET.get("end_date"), today)
    section_id = request.GET.get("section")
    selected_section = Section.objects.filter(id=section_id).first() if section_id else None

    if selected_section and not _ensure_permission(request.user, selected_section):
        return HttpResponseForbidden("Not allowed")

    ledgers = DailyLedger.objects.select_related("section", "item").filter(
        date__gte=start_date_val,
        date__lte=end_date_val,
        section__in=sections,
    )
    if selected_section:
        ledgers = ledgers.filter(section=selected_section)

    rows = []
    for ledger in ledgers.order_by("-date", "section__name", "item__name"):
        rows.append(
            {
                "date": ledger.date,
                "section": ledger.section,
                "item": ledger.item,
                "total_available": ledger.total_available,
                "waste_qty": ledger.waste_qty,
                "waste_percentage": ledger.waste_percentage,
            }
        )

    paginator = Paginator(rows, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "sections": sections,
        "selected_section": selected_section,
        "start_date": start_date_val,
        "end_date": end_date_val,
    }
    return render(request, "production/reports/wastage_report.html", context)


@login_required
def downtime_entry(request: HttpRequest) -> HttpResponse:
    if not _user_has_role(request.user, ROLE_SUPERVISOR):
        return HttpResponseForbidden("Only supervisors can log machine downtime")

    sections = _available_sections(request.user)
    initial_section_id = request.GET.get("section") or (sections.first().id if sections else None)
    initial_data = {
        "downtime_date": date.today(),
    }
    if initial_section_id:
        initial_data["section"] = initial_section_id

    if request.method == "POST":
        form = MachineDowntimeForm(request.POST, sections=sections, user=request.user)
        section = form.data.get("section")
        selected_section = Section.objects.filter(id=section).first() if section else None
        if selected_section and not _ensure_permission(request.user, selected_section):
            return HttpResponseForbidden("You are not allowed to log downtime for this section")

        if form.is_valid():
            entry = form.save(commit=False)
            entry.logged_by = request.user
            entry.save()
            messages.success(request, "Machine downtime logged successfully.")
            return redirect(
                f"{reverse('production:downtime-list')}?date={entry.downtime_date.isoformat()}&section={entry.machine.section_id}"
            )
    else:
        form = MachineDowntimeForm(initial=initial_data, sections=sections, user=request.user)

    return render(request, "production/downtime_entry_form.html", {"form": form})


@login_required
def downtime_list(request: HttpRequest) -> HttpResponse:
    sections = _available_sections(request.user)
    report_date = _coerce_date(request.GET.get("date"), date.today())
    section_id = request.GET.get("section")
    selected_section = Section.objects.filter(id=section_id).first() if section_id else None

    if selected_section and not _ensure_permission(request.user, selected_section):
        return HttpResponseForbidden("Not allowed")

    rows = MachineDowntime.objects.select_related("machine", "machine__section", "logged_by").filter(
        downtime_date=report_date,
        machine__section__in=sections,
    )
    if selected_section:
        rows = rows.filter(machine__section=selected_section)
    rows = rows.order_by("machine__section__name", "machine__name", "-start_time")

    paginator = Paginator(rows, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "report_date": report_date,
        "sections": sections,
        "selected_section": selected_section,
    }
    return render(request, "production/reports/downtime_list.html", context)
