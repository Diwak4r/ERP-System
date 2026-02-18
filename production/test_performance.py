import pytest
from datetime import date
from decimal import Decimal
from django.urls import reverse
from .models import Section, Worker, Item, TargetRule
from django.contrib.auth import get_user_model

pytestmark = pytest.mark.django_db

def test_production_entry_post_queries(client, django_assert_num_queries):
    User = get_user_model()
    admin = User.objects.create_user(username="admin", password="pass", is_superuser=True)
    section = Section.objects.create(name="Assembly", code="ASM")
    worker = Worker.objects.create(name="John", employee_code="W001")
    item1 = Item.objects.create(name="Widget 1", sku="ITM-001")
    item2 = Item.objects.create(name="Widget 2", sku="ITM-002")

    TargetRule.objects.create(section=section, item=item1, target_qty=Decimal("100"), shift_hours=Decimal("8"), start_date=date.today())
    TargetRule.objects.create(section=section, item=item2, target_qty=Decimal("200"), shift_hours=Decimal("8"), start_date=date.today())

    client.force_login(admin)

    # Let's say we have 5 entries
    num_entries = 5
    data = {
        "entry_date": date.today().isoformat(),
        "section": section.id,
        "form-TOTAL_FORMS": str(num_entries),
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }
    for i in range(num_entries):
        item = item1 if i % 2 == 0 else item2
        data[f"form-{i}-worker"] = worker.id
        data[f"form-{i}-item"] = item.id
        data[f"form-{i}-target_qty"] = "0"
        data[f"form-{i}-actual_qty"] = "10"
        data[f"form-{i}-shift_hours"] = "0"

    # With optimizations:
    # 1. TargetRule lookup: 1 query instead of N
    # 2. ProductionEntry save: 1 query instead of N
    # 3. Role/Session/Setup: ~3-5 queries
    # 4. Form validation (ChoiceField): ~4 per form (Django default behavior for ModelChoiceField)
    # Total for N=5: ~25 queries (Reduced from 33)
    # Total for N=20: ~85 queries (Reduced from 123)

    with django_assert_num_queries(25):
         resp = client.post(reverse("production:entry"), data=data)
         assert resp.status_code == 302
