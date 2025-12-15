from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "healthz/",
        TemplateView.as_view(template_name="healthz.html"),
        name="healthz",
    ),
    path("production/", include("production.urls")),
]
