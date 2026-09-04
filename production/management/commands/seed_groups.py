from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seeds the database with required RBAC groups (ADMIN, SUPERVISOR, STORE, VIEWER)"

    def handle(self, *args, **options):
        groups = ["ADMIN", "SUPERVISOR", "STORE", "VIEWER"]
        for group_name in groups:
            group, created = Group.objects.get_or_create(name=group_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created group: {group_name}"))
            else:
                self.stdout.write(self.style.WARNING(f"Group already exists: {group_name}"))

        self.stdout.write(self.style.SUCCESS("Group seeding completed successfully!"))
