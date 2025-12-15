from django.contrib import admin

from .models import Item, ProductionEntry, Section, TargetRule, Worker


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
