from django.contrib import admin
from django.forms import ModelForm, CharField
from .models import AuditEvent, DayLock, Item, ProductionEntry, Section, TargetRule, Worker
from django.core.serializers.json import DjangoJSONEncoder
import json
from .middleware import get_current_request


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


class ProductionEntryAdminForm(ModelForm):
    change_reason = CharField(required=True, help_text="Reason for this change.")
    class Meta:
        model = ProductionEntry
        fields = '__all__'


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def serialize_model_instance(obj):
    if not obj:
        return None
    data = {}
    for f in obj._meta.fields:
        if f.name in ["created_at", "updated_at"]:
            continue
        val = getattr(obj, f.name)
        if hasattr(val, 'pk'):
            data[f.name] = val.pk
        elif hasattr(val, 'quantize'):
            data[f.name] = str(val)
        else:
            data[f.name] = val
    return json.dumps(data, cls=DjangoJSONEncoder)


@admin.register(ProductionEntry)
class ProductionEntryAdmin(admin.ModelAdmin):
    form = ProductionEntryAdminForm
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
        action = "UPDATE" if change else "CREATE"
        before_data = None

        if change:
            try:
                old_obj = ProductionEntry.objects.get(pk=obj.pk)
                before_data = serialize_model_instance(old_obj)
            except ProductionEntry.DoesNotExist:
                pass

        super().save_model(request, obj, form, change)

        after_data = serialize_model_instance(obj)

        req = get_current_request()
        ip = get_client_ip(req) if req else None

        AuditEvent.objects.create(
            actor=request.user,
            action=action,
            model_name="ProductionEntry",
            object_id=str(obj.pk),
            before_data=before_data,
            after_data=after_data,
            reason=form.cleaned_data.get("change_reason", ""),
            ip=ip
        )

    def delete_model(self, request, obj):
        before_data = serialize_model_instance(obj)

        req = get_current_request()
        ip = get_client_ip(req) if req else None

        # We need a reason, but delete_model doesn't have a form.
        # For simplicity in this demo, we'll log it as "Deleted via admin".
        reason = "Deleted via admin"

        AuditEvent.objects.create(
            actor=request.user,
            action="DELETE",
            model_name="ProductionEntry",
            object_id=str(obj.pk),
            before_data=before_data,
            after_data=None,
            reason=reason,
            ip=ip
        )
        super().delete_model(request, obj)


@admin.register(DayLock)
class DayLockAdmin(admin.ModelAdmin):
    list_display = ("section", "lock_date", "locked_at", "locked_by", "is_locked")
    list_filter = ("section", "lock_date", "is_locked")
    search_fields = ("section__name",)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("actor", "action", "model_name", "object_id", "timestamp", "ip")
    list_filter = ("action", "model_name", "timestamp")
    search_fields = ("actor__username", "model_name", "object_id")
    readonly_fields = [f.name for f in AuditEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
