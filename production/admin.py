from django.contrib import admin

import json
from .models import Item, ProductionEntry, Section, TargetRule, Worker, DayLock, AuditEvent, ProcessFlowEdge, DailyLedger
from .middleware import get_current_request

def _create_audit_event(request, action, obj, before_dict=None):
    from django.core.serializers.json import DjangoJSONEncoder
    import datetime
    from decimal import Decimal
    from django.db.models import Model

    class CustomJSONEncoder(DjangoJSONEncoder):
        def default(self, o):
            if isinstance(o, Model):
                return str(o.pk)
            return super().default(o)

    after_dict = None
    if obj.pk:
        # crude representation, but sufficient for an MVP
        after_dict = {f.name: getattr(obj, f.name) for f in obj._meta.fields if hasattr(obj, f.name)}
        # make it JSON serializable
        after_json = json.loads(json.dumps(after_dict, cls=CustomJSONEncoder))
    else:
        after_json = None

    before_json = None
    if before_dict:
        before_json = json.loads(json.dumps(before_dict, cls=CustomJSONEncoder))

    ip = getattr(request, 'client_ip', None)

    AuditEvent.objects.create(
        actor=request.user,
        action=action,
        model_name=obj.__class__.__name__,
        object_id=str(obj.pk) if obj.pk else "",
        before_json=before_json,
        after_json=after_json,
        ip=ip
    )


class AuditedModelAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        before_dict = None
        if change:
            old_obj = obj.__class__.objects.get(pk=obj.pk)
            before_dict = {f.name: getattr(old_obj, f.name) for f in old_obj._meta.fields if hasattr(old_obj, f.name)}

        super().save_model(request, obj, form, change)

        action = "UPDATE" if change else "CREATE"
        _create_audit_event(request, action, obj, before_dict)

    def delete_model(self, request, obj):
        before_dict = {f.name: getattr(obj, f.name) for f in obj._meta.fields if hasattr(obj, f.name)}
        _create_audit_event(request, "DELETE", obj, before_dict)
        super().delete_model(request, obj)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    search_fields = ("name", "code")
    filter_horizontal = ("supervisors",)


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("name", "employee_code", "is_active")
    search_fields = ("name", "employee_code")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "unit", "is_active")
    search_fields = ("name", "sku")
    list_filter = ("unit", "is_active")


@admin.register(TargetRule)
class TargetRuleAdmin(admin.ModelAdmin):
    list_display = ("section", "item", "target_qty", "shift_hours", "start_date", "end_date")
    search_fields = ("section__name", "item__name")
    list_filter = ("section", "item")


@admin.register(DayLock)
class DayLockAdmin(AuditedModelAdmin):
    list_display = ("section", "lock_date", "is_locked", "locked_by", "locked_at")
    list_filter = ("section", "lock_date", "is_locked")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "actor", "action", "model_name", "object_id")
    list_filter = ("action", "model_name", "timestamp")
    search_fields = ("actor__username", "object_id")
    readonly_fields = ("timestamp", "actor", "action", "model_name", "object_id", "before_json", "after_json", "reason", "ip")


@admin.register(ProcessFlowEdge)
class ProcessFlowEdgeAdmin(admin.ModelAdmin):
    list_display = ("item", "from_section", "to_section", "lead_days")
    list_filter = ("from_section", "to_section")


@admin.register(DailyLedger)
class DailyLedgerAdmin(admin.ModelAdmin):
    list_display = ("date", "section", "item", "opening_balance", "received_from_prev", "manual_received", "output", "closing_balance")
    list_filter = ("date", "section", "item")
    readonly_fields = ("closing_balance",)


@admin.register(ProductionEntry)
class ProductionEntryAdmin(AuditedModelAdmin):
    list_display = (
        "entry_date",
        "section",
        "worker",
        "item",
        "target_qty",
        "actual_qty",
        "shift_hours",
        "overtime_hours",
        "target_met",
    )
    list_filter = ("entry_date", "section", "item", "worker")
    search_fields = ("worker__name", "item__name")
    readonly_fields = ("created_at", "updated_at", "created_by")
