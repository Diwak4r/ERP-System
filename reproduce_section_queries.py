import os
import django
from datetime import date

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth.models import User, Group
from django.db import connection
from django.test import RequestFactory
from production.models import Section
from production.views import production_entry, production_entry_row, production_entries, ROLE_SUPERVISOR

def reproduce_section_queries():
    # Setup
    User.objects.filter(username="test_sec_user").delete()
    user = User.objects.create_user(username="test_sec_user")
    supervisor_group, _ = Group.objects.get_or_create(name=ROLE_SUPERVISOR)
    user.groups.add(supervisor_group)

    section = Section.objects.create(name="Test Section", code="TS1")
    section.supervisors.add(user)

    rf = RequestFactory()

    print("Checking queries in production_entry...")
    request = rf.get(f"/production/entry/?section={section.id}")
    request.user = user
    connection.queries_log.clear()
    production_entry(request)
    # Expected: 1 for group names cache, 1 for available sections list. Total 2.
    # (Excluding session and auth which might trigger on first access if not careful, but RequestFactory + user object should be fine)
    q_count = len(connection.queries)
    print(f"Number of queries in production_entry: {q_count}")
    for q in connection.queries:
        print(f"  - {q['sql']}")

    print("\nChecking queries in production_entry_row...")
    request = rf.get(f"/production/entry/row/?section={section.id}")
    request.user = user
    connection.queries_log.clear()
    production_entry_row(request)
    q_count = len(connection.queries)
    print(f"Number of queries in production_entry_row: {q_count}")
    for q in connection.queries:
        print(f"  - {q['sql']}")

    print("\nChecking queries in production_entries...")
    request = rf.get(f"/production/entries/?section={section.id}")
    request.user = user
    connection.queries_log.clear()
    production_entries(request)
    q_count = len(connection.queries)
    print(f"Number of queries in production_entries: {q_count}")
    # production_entries also has the main entries query
    for q in connection.queries:
        print(f"  - {q['sql']}")

if __name__ == "__main__":
    reproduce_section_queries()
