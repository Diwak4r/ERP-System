from django.contrib import admin

from .models import Item, ProductionEntry, Section, Worker


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    search_fields = ("name", "code")


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("name", "employee_code", "is_daily_wage", "is_active")
    search_fields = ("name", "employee_code")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "unit", "is_active")
    search_fields = ("name", "sku")


@admin.register(ProductionEntry)
class ProductionEntryAdmin(admin.ModelAdmin):
    list_display = (
        "entry_date",
        "section",
        "worker",
        "item",
        "target_qty",
        "actual_qty",
        "target_met",
    )
    list_filter = ("entry_date", "section", "item", "target_met")
    search_fields = ("worker__name", "item__name")
