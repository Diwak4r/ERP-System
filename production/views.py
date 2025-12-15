from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from .forms import ProductionEntryForm, ProductionEntryFormSet
from .models import Item, ProductionEntry, Section, TargetRule, Worker

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
    sections = _available_sections(request.user)
    section_id = request.GET.get("section")
    entry_date_str = request.GET.get("entry_date")
    form_count = int(request.GET.get("form_count", 0))
    section = get_object_or_404(Section, id=section_id) if section_id else None
    if section and not _ensure_permission(request.user, section):
        return HttpResponseForbidden("Not allowed")
    entry_date_val = date.fromisoformat(entry_date_str) if entry_date_str else date.today()
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
    entry_date_val = date.fromisoformat(entry_date_str) if entry_date_str else date.today()
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
