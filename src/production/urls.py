from django.urls import path
from . import views

app_name = "production"

urlpatterns = [
    path("reports/daily-section/", views.daily_section_summary, name="daily_section"),
    path("reports/item-aggregate/", views.item_aggregate_report, name="item_aggregate"),
    path("reports/worker-history/", views.worker_history, name="worker_history"),
]
