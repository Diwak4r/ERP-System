from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django import forms
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.db import transaction
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.db.models import Sum, F, ExpressionWrapper, FloatField, Case, When, Value, BooleanField
from django.db.models.functions import Cast

from .models import AttendanceLine, AttendanceSheet
from .forms import ProductionEntryForm, ProductionEntryFormSet, WasteEntryForm, WasteEntryFormSet, AttendanceLineForm, BaseAttendanceLineFormSet
from .models import DailyLedger, Item, ProductionEntry, Section, TargetRule, WasteEntry, Worker

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
@require_http_methods(["GET", "POST"])
def attendance_entry(request: HttpRequest) -> HttpResponse:
    user = request.user
    sections = _available_sections(user)
    if not sections:
        return HttpResponseForbidden("You don't have access to any sections.")

    attendance_date_str = request.GET.get("attendance_date") or request.POST.get("attendance_date")
    attendance_date = _coerce_date(attendance_date_str, date.today())

    section_id_str = request.GET.get("section") or request.POST.get("section")
    try:
        section_id = int(section_id_str) if section_id_str else sections[0].id
    except ValueError:
        section_id = sections[0].id

    selected_section = next((s for s in sections if s.id == section_id), None)
    if not selected_section:
        return HttpResponseForbidden("You don't have access to this section.")

    AttendanceFormSet = forms.formset_factory(
        AttendanceLineForm,
        formset=BaseAttendanceLineFormSet,
        extra=0,
        can_delete=True,
    )

    if request.method == "POST":
        formset = AttendanceFormSet(
            request.POST,
            form_kwargs={"section": selected_section, "attendance_date": attendance_date},
        )
        if formset.is_valid():
            try:
                with transaction.atomic():
                    # Attempt to get or create the sheet
                    sheet, created = AttendanceSheet.objects.get_or_create(
                        attendance_date=attendance_date,
                        section=selected_section,
                        defaults={"created_by": request.user}
                    )

                    # Ensure DayLock validation is triggered
                    sheet.clean()

                    # Delete existing lines if this is an update to avoid duplicates if workers change
                    if not created:
                        AttendanceLine.objects.filter(sheet=sheet).delete()

                    lines_to_create = []
                    for form in formset.forms:
                        if formset.can_delete and formset._should_delete_form(form):
                            continue
                        worker = form.cleaned_data.get("worker")
                        is_present = form.cleaned_data.get("is_present", True)
                        notes = form.cleaned_data.get("notes", "")

                        if worker:
                            line = AttendanceLine(
                                sheet=sheet,
                                worker=worker,
                                is_present=is_present,
                                notes=notes
                            )
                            lines_to_create.append(line)

                    if lines_to_create:
                        AttendanceLine.objects.bulk_create(lines_to_create)

                messages.success(request, f"Attendance saved successfully for {attendance_date}.")
                redirect_url = reverse("production:attendance-entry")
                return redirect(f"{redirect_url}?attendance_date={attendance_date}&section={selected_section.id}")

            except ValidationError as e:
                if hasattr(e, "messages"):
                    for msg in e.messages:
                        messages.error(request, msg)
                else:
                    messages.error(request, str(e))
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        # Check if we already have attendance for this day/section to populate it
        existing_sheet = AttendanceSheet.objects.filter(
            attendance_date=attendance_date, section=selected_section
        ).first()

        initial_data = []
        if existing_sheet:
             for line in existing_sheet.lines.select_related('worker').all():
                 initial_data.append({
                     'worker': line.worker_id,
                     'is_present': line.is_present,
                     'notes': line.notes
                 })
        else:
             # Auto-populate all active workers
             workers = Worker.objects.filter(is_active=True).order_by('name')
             for w in workers:
                 initial_data.append({
                     'worker': w.id,
                     'is_present': True,
                     'notes': ''
                 })

        formset = AttendanceFormSet(
            initial=initial_data,
            form_kwargs={"section": selected_section, "attendance_date": attendance_date},
        )
        if initial_data:
            formset.extra = len(initial_data)

    context = {
        "formset": formset,
        "attendance_date": attendance_date,
        "sections": sections,
        "selected_section": selected_section,
    }
    return render(request, "production/attendance_entry_form.html", context)


@login_required
@require_http_methods(["GET"])
def attendance_entry_row(request: HttpRequest) -> HttpResponse:
    try:
        form_count = int(request.GET.get("form_count", 0))
    except ValueError:
        form_count = 0

    section_id = request.GET.get("section")
    attendance_date_str = request.GET.get("attendance_date")

    section = None
    if section_id:
        try:
            section = Section.objects.get(id=section_id)
        except Section.DoesNotExist:
            pass

    attendance_date = _coerce_date(attendance_date_str, date.today())

    form = AttendanceLineForm(
        prefix=f"form-{form_count}",
        section=section,
        attendance_date=attendance_date,
    )
    # Pre-evaluate choices for performance
    worker_qs = Worker.objects.filter(is_active=True)
    form.fields["worker"].choices = [("", "---------")] + [(w.pk, str(w)) for w in worker_qs]

    context = {
        "form": form,
        "index": form_count,
        "next_index": form_count + 1,
    }
    return render(request, "production/attendance_entry_row.html", context)


@login_required
@require_http_methods(["GET"])
def attendance_report(request: HttpRequest) -> HttpResponse:
    user = request.user
    sections = _available_sections(user)

    attendance_date_str = request.GET.get("attendance_date")
    attendance_date = _coerce_date(attendance_date_str, date.today())

    sheets = AttendanceSheet.objects.filter(
        attendance_date=attendance_date,
        section__in=sections
    ).select_related('section').prefetch_related('lines')

    report_data = []
    total_present = 0
    total_absent = 0

    for sheet in sheets:
        lines = list(sheet.lines.all())
        present_count = sum(1 for line in lines if line.is_present)
        absent_count = len(lines) - present_count

        total_present += present_count
        total_absent += absent_count

        report_data.append({
            'section': sheet.section,
            'present_count': present_count,
            'absent_count': absent_count,
            'total_count': len(lines)
        })

    context = {
        "report_data": report_data,
        "total_present": total_present,
        "total_absent": total_absent,
        "attendance_date": attendance_date,
    }
    return render(request, "production/reports/attendance_report.html", context)
