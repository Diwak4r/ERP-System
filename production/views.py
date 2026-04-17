from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.db.models import Sum, F, ExpressionWrapper, FloatField, Case, When, Value, BooleanField
from django.db.models.functions import Cast

from .forms import ProductionEntryForm, ProductionEntryFormSet, WasteEntryForm
from .models import Item, ProductionEntry, Section, TargetRule, Worker, DailyLedger

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
def ledger_list(request: HttpRequest) -> HttpResponse:
    sections = _available_sections(request.user)
    date_str = request.GET.get("date")
    section_id = request.GET.get("section")

    try:
        ledger_date = date.fromisoformat(date_str) if date_str else date.today()
    except ValueError:
        ledger_date = date.today()

    selected_section = Section.objects.filter(id=section_id).first() if section_id else None

    if selected_section and not _ensure_permission(request.user, selected_section):
        return HttpResponseForbidden("Not allowed")

    ledgers = DailyLedger.objects.filter(date=ledger_date)
    if selected_section:
        ledgers = ledgers.filter(section=selected_section)
    elif sections:
         ledgers = ledgers.filter(section__in=sections)

    ledgers = ledgers.select_related("section", "item").order_by("section__name", "item__name")

    # Add anomaly flag for template
    for ledger in ledgers:
        available = ledger.opening_balance + ledger.received_from_prev + ledger.manual_received
        ledger.is_anomaly = ledger.output_qty > available

    context = {
        "ledgers": ledgers,
        "ledger_date": ledger_date,
        "sections": sections,
        "selected_section": selected_section,
    }
    return render(request, "production/ledger_list.html", context)



@login_required
def waste_entry(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = WasteEntryForm(request.POST, user=request.user)
        if form.is_valid():
            # Get or create ledger and update waste
            ledger, created = DailyLedger.objects.get_or_create(
                date=form.cleaned_data["date"],
                section=form.cleaned_data["section"],
                item=form.cleaned_data["item"],
            )
            # Try to save to invoke form validation logic again or just update
            ledger.waste_qty = form.cleaned_data["waste_qty"]
            ledger.save(update_fields=["waste_qty"])
            messages.success(request, f"Wastage updated for {ledger.item.name} in {ledger.section.name}")
            return redirect("production:waste-entry")
    else:
        form = WasteEntryForm(user=request.user, initial={"date": date.today()})

    context = {
        "form": form,
    }
    return render(request, "production/waste_entry.html", context)

@login_required
def wastage_report(request: HttpRequest) -> HttpResponse:
    sections = _available_sections(request.user)
    date_str = request.GET.get("date")
    section_id = request.GET.get("section")

    try:
        report_date = date.fromisoformat(date_str) if date_str else date.today()
    except ValueError:
        report_date = date.today()

    selected_section = Section.objects.filter(id=section_id).first() if section_id else None

    if selected_section and not _ensure_permission(request.user, selected_section):
        return HttpResponseForbidden("Not allowed")

    ledgers = DailyLedger.objects.filter(date=report_date)
    if selected_section:
        ledgers = ledgers.filter(section=selected_section)
    elif sections:
         ledgers = ledgers.filter(section__in=sections)

    ledgers = ledgers.select_related("section", "item").order_by("section__name", "item__name")

    for ledger in ledgers:
        total_available = ledger.opening_balance + ledger.received_from_prev + ledger.manual_received
        if total_available > 0:
            ledger.waste_percent = (ledger.waste_qty / total_available) * 100
        else:
            ledger.waste_percent = Decimal("0.00")

    context = {
        "ledgers": ledgers,
        "report_date": report_date,
        "sections": sections,
        "selected_section": selected_section,
    }
    return render(request, "production/reports/wastage_report.html", context)
