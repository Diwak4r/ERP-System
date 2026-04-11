from django.urls import path

from . import views

app_name = "production"
urlpatterns = [
    path("entry/", views.production_entry, name="entry"),
    path("entries/", views.production_entries, name="entries"),
    path("entry/row/", views.production_entry_row, name="entry-row"),
    path("reports/daily-section/", views.daily_section_summary, name="report-daily-section"),
    path("reports/item-aggregate/", views.item_aggregate, name="report-item-aggregate"),
    path("reports/worker-history/<int:worker_id>/", views.worker_history, name="report-worker-history"),
]
