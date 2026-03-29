import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth.models import User, Group
from django.db import connection
from production.views import _user_has_role, ROLE_SUPERVISOR

def reproduce_rbac_queries():
    # Setup
    User.objects.filter(username="testsupervisor_new").delete()
    user = User.objects.create_user(username="testsupervisor_new")
    supervisor_group, _ = Group.objects.get_or_create(name=ROLE_SUPERVISOR)
    user.groups.add(supervisor_group)

    # Clear queries
    connection.queries_log.clear()

    print("Checking RBAC queries...")

    # Call multiple times
    _user_has_role(user, ROLE_SUPERVISOR)
    _user_has_role(user, ROLE_SUPERVISOR)
    _user_has_role(user, ROLE_SUPERVISOR)

    query_count = len(connection.queries)
    print(f"Number of queries for 3 role checks: {query_count}")
    for q in connection.queries:
        print(f"  - {q['sql']}")

    if query_count == 1:
        print("SUCCESS: RBAC checks are optimized to use only 1 query.")
    else:
        print(f"FAILURE: Expected 1 query, but got {query_count}.")

if __name__ == "__main__":
    reproduce_rbac_queries()
