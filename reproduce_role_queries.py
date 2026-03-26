import os
import django
from django.conf import settings

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth.models import User, Group
from django.test import RequestFactory
from production.views import production_entry_row, ROLE_SUPERVISOR
from production.models import Section
from django.db import connection
from django.test.utils import CaptureQueriesContext

def setup_data():
    User.objects.all().delete()
    Section.objects.all().delete()
    Group.objects.all().delete()

    supervisor = User.objects.create_user(username="supervisor", password="pass")
    group = Group.objects.create(name=ROLE_SUPERVISOR)
    supervisor.groups.add(group)

    section = Section.objects.create(name="Test Section", code="TS")
    section.supervisors.add(supervisor)
    return supervisor, section

def benchmark():
    supervisor, section = setup_data()
    factory = RequestFactory()
    url = f"/production/entry/row/?section={section.id}&form_count=1"
    request = factory.get(url)
    request.user = supervisor

    with CaptureQueriesContext(connection) as queries:
        response = production_entry_row(request)
        assert response.status_code == 200

    print(f"Total queries: {len(queries)}")
    for i, q in enumerate(queries):
        print(f"Query {i+1}: {q['sql']}")

if __name__ == "__main__":
    benchmark()
