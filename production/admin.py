import json
from decimal import Decimal
from django.contrib import admin
from django.core.serializers.json import DjangoJSONEncoder

from .models import Item, ProductionEntry, Section, TargetRule, Worker, DayLock, AuditEvent, ProcessFlowEdge, DailyLedger
from .middleware import get_current_request_ip

def _serialize_model(obj):
    if not obj or not obj.pk:
        return None
    data = {}
    for field in obj._meta.fields:
        if field.name in ('created_at', 'updated_at', 'locked_at', 'timestamp'):
            continue
        val = getattr(obj, field.name)
        if hasattr(val, 'pk'):
             val = val.pk
        elif isinstance(val, Decimal):
            val = str(val)
        data[field.name] = val
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))

def _log_audit_event(request, obj, action, before_data=None):
    AuditEvent.objects.create(
        actor=request.user,
        action=action,
        model_name=obj.__class__.__name__,
        object_id=str(obj.pk),
        before_data=before_data,
        after_data=_serialize_model(obj) if action != 'DELETE' else None,
        reason="Admin Override",
        ip_address=get_current_request_ip()
    )


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


@admin.register(ProductionEntry)
class ProductionEntryAdmin(admin.ModelAdmin):
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

    def save_model(self, request, obj, form, change):
        before_data = None
        if change:
            old_obj = ProductionEntry.objects.get(pk=obj.pk)
            before_data = _serialize_model(old_obj)
        super().save_model(request, obj, form, change)
        action = "UPDATE" if change else "CREATE"
        _log_audit_event(request, obj, action, before_data)

    def delete_model(self, request, obj):
        before_data = _serialize_model(obj)
        super().delete_model(request, obj)
        _log_audit_event(request, obj, "DELETE", before_data)


@admin.register(DayLock)
class DayLockAdmin(admin.ModelAdmin):
    list_display = ("section", "lock_date", "is_locked", "locked_by", "locked_at")
    list_filter = ("section", "lock_date", "is_locked")

    def save_model(self, request, obj, form, change):
        before_data = None
        if change:
            old_obj = DayLock.objects.get(pk=obj.pk)
            before_data = _serialize_model(old_obj)

            # Auto-assign locked_by if locking/unlocking
            if obj.is_locked != old_obj.is_locked:
                obj.locked_by = request.user
        else:
            if obj.is_locked:
                 obj.locked_by = request.user

        super().save_model(request, obj, form, change)
        action = "UPDATE" if change else "CREATE"
        _log_audit_event(request, obj, action, before_data)

    def delete_model(self, request, obj):
        before_data = _serialize_model(obj)
        super().delete_model(request, obj)
        _log_audit_event(request, obj, "DELETE", before_data)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "actor", "action", "model_name", "object_id", "ip_address")
    list_filter = ("action", "model_name", "timestamp")
    search_fields = ("actor__username", "model_name", "object_id")
    readonly_fields = ("actor", "action", "model_name", "object_id", "before_data", "after_data", "reason", "timestamp", "ip_address")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(ProcessFlowEdge)
class ProcessFlowEdgeAdmin(admin.ModelAdmin):
    list_display = ("item", "from_section", "to_section", "lead_days")
    list_filter = ("from_section", "to_section", "item")

@admin.register(DailyLedger)
class DailyLedgerAdmin(admin.ModelAdmin):
    list_display = ("date", "section", "item", "opening_balance", "received_from_prev", "manual_received", "output_qty", "waste_qty", "closing_balance")
    list_filter = ("date", "section", "item")
    readonly_fields = ("closing_balance",)
