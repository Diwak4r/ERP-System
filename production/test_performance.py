from datetime import date
from decimal import Decimal
import pytest
from django.urls import reverse
from .models import Section, Worker, Item, TargetRule
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

@pytest.mark.django_db
def test_production_entry_query_count(client, django_assert_num_queries):
    User = get_user_model()
    admin_user = User.objects.create_superuser(username="admin", password="pass")

    section = Section.objects.create(name="Assembly", code="ASM")
    worker1 = Worker.objects.create(name="Worker 1", employee_code="W1")
    worker2 = Worker.objects.create(name="Worker 2", employee_code="W2")
    item1 = Item.objects.create(name="Item 1", sku="I1")
    item2 = Item.objects.create(name="Item 2", sku="I2")

    TargetRule.objects.create(section=section, item=item1, target_qty=Decimal("100"), shift_hours=Decimal("8"), start_date=date.today())
    TargetRule.objects.create(section=section, item=item2, target_qty=Decimal("200"), shift_hours=Decimal("8"), start_date=date.today())

    client.force_login(admin_user)

    data = {
        "entry_date": date.today().isoformat(),
        "section": section.id,
        "form-TOTAL_FORMS": "2",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
        "form-0-worker": worker1.id,
        "form-0-item": item1.id,
        "form-0-actual_qty": "110",
        "form-1-worker": worker2.id,
        "form-1-item": item2.id,
        "form-1-actual_qty": "210",
    }

    # Let's see how many queries it takes
    # Original query count: 18 for 2 forms
    # Optimized query count: 15 for 2 forms
    # Savings: 1 (TargetRule) + 2 (Worker choices) + 2 (Item choices) - 2 (Initial choices fetch) = 3 queries saved for 2 forms.
    # For N forms, savings: (N-1) + 2*(N-1) + 2*(N-1) = 5*(N-1) queries saved?
    # Actually, ModelChoiceField still does 1 existence query per field during validation.
    with django_assert_num_queries(15):
         client.post(reverse("production:entry"), data=data)
