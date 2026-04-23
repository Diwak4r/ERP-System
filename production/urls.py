from django.urls import path

from . import views

app_name = "production"
urlpatterns = [
    path("entry/", views.production_entry, name="entry"),
    path("entries/", views.production_entries, name="entries"),
    path("entry/row/", views.production_entry_row, name="entry-row"),
    path("requisitions/new/", views.requisition_create, name="requisition-create"),
    path("requisitions/", views.requisition_list, name="requisition-list"),
    path("requisitions/<int:requisition_id>/", views.requisition_detail, name="requisition-detail"),
    path("requisitions/pending-badge/", views.requisition_pending_badge, name="requisition-pending-badge"),
    path("attendance/entry/", views.attendance_entry, name="attendance-entry"),
    path("downtime/entry/", views.downtime_entry, name="downtime-entry"),
    path("waste/entry/", views.waste_entry, name="waste-entry"),
    path("waste/entry/row/", views.waste_entry_row, name="waste-entry-row"),
    path("reports/daily-section/", views.daily_section_summary, name="report-daily-section"),
    path("reports/attendance/", views.attendance_report, name="report-attendance"),
    path("reports/downtime/", views.downtime_list, name="downtime-list"),
    path("reports/item-aggregate/", views.item_aggregate, name="report-item-aggregate"),
    path("reports/wastage/", views.wastage_report, name="report-wastage"),
    path("reports/worker-history/<int:worker_id>/", views.worker_history, name="report-worker-history"),
]
