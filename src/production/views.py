import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Sum, Case, When, Value, IntegerField, BooleanField, F
from django.shortcuts import get_object_or_404, render
from django.utils.dateparse import parse_date

from .models import Item, ProductionEntry, Section, Worker


def _parse_date(param: str | None, default: date) -> date:
    if not param:
        return default
    parsed = parse_date(param)
    return parsed or default


def daily_section_summary(request):
    sections = Section.objects.filter(is_active=True).order_by("name")
    selected_date = _parse_date(request.GET.get("date"), date.today())
    section_id = request.GET.get("section")
    section = None
    if section_id:
        section = get_object_or_404(Section, pk=section_id)
    elif sections:
        section = sections.first()

    entries = ProductionEntry.objects.filter(entry_date=selected_date)
    if section:
        entries = entries.filter(section=section)

    entries = entries.select_related("worker", "item", "section")

    per_item = entries.values("item__id", "item__name").annotate(total_actual=Sum("actual_qty")).order_by("item__name")
    per_worker = (
        entries.values("worker__id", "worker__name")
        .annotate(total_actual=Sum("actual_qty"))
        .order_by("worker__name")
    )
    worker_count = entries.values("worker_id").distinct().count()

    context = {
        "sections": sections,
        "selected_date": selected_date,
        "selected_section": section,
        "per_item": per_item,
        "per_worker": per_worker,
        "worker_count": worker_count,
        "entries": entries,
    }
    return render(request, "production/reports/daily_section.html", context)


def item_aggregate_report(request):
    sections = Section.objects.filter(is_active=True).order_by("name")
    selected_date = _parse_date(request.GET.get("date"), date.today())
    section_id = request.GET.get("section")
    section = None
    if section_id:
        section = get_object_or_404(Section, pk=section_id)
    elif sections:
        section = sections.first()

    entries = ProductionEntry.objects.filter(entry_date=selected_date)
    if section:
        entries = entries.filter(section=section)
    entries = entries.select_related("item", "section")

    aggregate = (
        entries.values("item__id", "item__name")
        .annotate(
            total_target=Sum("target_qty"),
            total_actual=Sum("actual_qty"),
            hit_count=Sum(Case(When(target_met=True, then=1), default=0, output_field=IntegerField())),
            entry_count=Count("id"),
        )
        .order_by("item__name")
    )

    for row in aggregate:
        if row["entry_count"]:
            row["hit_rate"] = round((row["hit_count"] / row["entry_count"]) * 100, 2)
        else:
            row["hit_rate"] = 0

    context = {
        "sections": sections,
        "selected_date": selected_date,
        "selected_section": section,
        "aggregate": aggregate,
    }
    return render(request, "production/reports/item_aggregate.html", context)


def worker_history(request):
    sections = Section.objects.filter(is_active=True).order_by("name")
    workers = Worker.objects.filter(is_active=True).order_by("name")

    section = None
    worker = None

    if request.GET.get("section"):
        section = get_object_or_404(Section, pk=request.GET.get("section"))
    elif sections:
        section = sections.first()

    if request.GET.get("worker"):
        worker = get_object_or_404(Worker, pk=request.GET.get("worker"))
    elif workers:
        worker = workers.first()

    start_date = _parse_date(request.GET.get("start"), date.today() - timedelta(days=6))
    end_date = _parse_date(request.GET.get("end"), date.today())

    entries = ProductionEntry.objects.filter(entry_date__range=(start_date, end_date))
    if section:
        entries = entries.filter(section=section)
    if worker:
        entries = entries.filter(worker=worker)

    per_day = (
        entries.values("entry_date")
        .annotate(
            total_target=Sum("target_qty"),
            total_actual=Sum("actual_qty"),
        )
        .order_by("entry_date")
    )

    daily_rows = []
    chart_labels = []
    chart_targets = []
    chart_actuals = []
    for row in per_day:
        total_target = row.get("total_target") or Decimal("0")
        total_actual = row.get("total_actual") or Decimal("0")
        target_met = total_actual >= total_target if total_target else False
        daily_rows.append(
            {
                "date": row["entry_date"],
                "total_target": total_target,
                "total_actual": total_actual,
                "target_met": target_met,
            }
        )
        chart_labels.append(row["entry_date"].strftime("%Y-%m-%d"))
        chart_targets.append(float(total_target))
        chart_actuals.append(float(total_actual))

    chart_data = {
        "labels": chart_labels,
        "targets": chart_targets,
        "actuals": chart_actuals,
    }

    context = {
        "sections": sections,
        "workers": workers,
        "selected_section": section,
        "selected_worker": worker,
        "start_date": start_date,
        "end_date": end_date,
        "daily_rows": daily_rows,
        "chart_json": json.dumps(chart_data),
    }
    return render(request, "production/reports/worker_history.html", context)
