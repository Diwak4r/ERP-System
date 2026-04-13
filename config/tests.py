import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_healthz_endpoint_ok(client):
    response = client.get(reverse("healthz"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}

