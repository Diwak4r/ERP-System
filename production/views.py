from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.db import transaction
from django.db.models import Sum, F, ExpressionWrapper, FloatField, Case, When, Value, BooleanField, Count, Q
from django.db.models.functions import Cast

from .forms import MachineDowntimeForm, AttendanceEntryForm, ProductionEntryForm, ProductionEntryFormSet, WasteEntryForm, WasteEntryFormSet
from .models import Machine, MachineDowntime, AttendanceLine, AttendanceSheet, DailyLedger, Item, ProductionEntry, Section, TargetRule, WasteEntry, Worker

ROLE_ADMIN = "ADMIN"
ROLE_SUPERVISOR = "SUPERVISOR"


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

    context = {
        "sections": sections,
        "selected_section": selected_section,
        "entry_date": entry_date_val,
        "item_summary": item_summary,
        "worker_summary": worker_summary,
        "worker_count": worker_count,
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

    context = {
        "rows": rows,
        "sections": sections,
        "selected_section": selected_section,
        "start_date": start_date_val,
        "end_date": end_date_val,
    }
    return render(request, "production/reports/wastage_report.html", context)


@login_required
def downtime_entry(request: HttpRequest) -> HttpResponse:
    today = date.today()
    sections = _available_sections(request.user)

    initial_date = _coerce_date(request.POST.get("downtime_date") or request.GET.get("downtime_date"), today)

    if request.method == "POST":
        form = MachineDowntimeForm(request.POST, sections=sections)
        if form.is_valid():
            # RBAC check: Ensure machine belongs to an allowed section
            machine = form.cleaned_data["machine"]
            if not _ensure_permission(request.user, machine.section):
                return HttpResponseForbidden("Not allowed to log downtime for this machine.")

            entry = form.save(commit=False)
            entry.logged_by = request.user
            entry.save()

            messages.success(request, f"Downtime logged for {machine.name}.")
            return redirect("production:downtime-list")
    else:
        form = MachineDowntimeForm(sections=sections, initial={"downtime_date": initial_date})

    context = {
        "form": form,
    }
    return render(request, "production/downtime_entry_form.html", context)


@login_required
def downtime_list(request: HttpRequest) -> HttpResponse:
    today = date.today()
    sections = _available_sections(request.user)
    report_date = _coerce_date(request.GET.get("date"), today)
    section_id = request.GET.get("section")

    selected_section = Section.objects.filter(id=section_id).first() if section_id else None

    if selected_section and not _ensure_permission(request.user, selected_section):
        return HttpResponseForbidden("Not allowed")

    machines = Machine.objects.filter(section__in=sections, is_active=True)
    if selected_section:
        machines = machines.filter(section=selected_section)

    # Get downtimes for the date
    downtimes = MachineDowntime.objects.select_related("machine").filter(
        downtime_date=report_date,
        machine__in=machines,
    )

    # Create a mapping to quickly highlight machines with downtime
    down_machine_ids = set(downtimes.values_list("machine_id", flat=True))

    context = {
        "report_date": report_date,
        "sections": sections,
        "selected_section": selected_section,
        "downtimes": downtimes.order_by("machine__name", "start_time"),
        "down_machine_ids": down_machine_ids,
        "machines": machines,
    }
    return render(request, "production/reports/downtime_list.html", context)
