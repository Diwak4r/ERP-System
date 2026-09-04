from django.contrib import admin
from django.db import connections
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView


def healthz(request):
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        payload = {"status": "ok", "database": "ok"}
        status = 200
    except Exception:
        payload = {"status": "degraded", "database": "error"}
        status = 503
    return JsonResponse(payload, status=status)

urlpatterns = [
    path("", RedirectView.as_view(url="/production/entry/", permanent=False), name="home"),
    path("admin/", admin.site.urls),
    path("production/", include("production.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("healthz", healthz, name="healthz"),
    path("healthz/", healthz, name="healthz-slash"),
]
