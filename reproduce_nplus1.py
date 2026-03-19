import os
import django
from datetime import date
from decimal import Decimal

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from production.models import Section, Worker, Item, TargetRule
from production.forms import ProductionEntryFormSet

User = get_user_model()

def reproduce():
    # Cleanup
    Section.objects.all().delete()
    Worker.objects.all().delete()
    Item.objects.all().delete()
    TargetRule.objects.all().delete()
    User.objects.all().delete()

    # Setup data
    user = User.objects.create_user(username='testuser', password='password')
    section = Section.objects.create(name='Section 1', code='S1')
    workers = [Worker.objects.create(name=f'Worker {i}', employee_code=f'W{i}', is_active=True) for i in range(5)]
    items = [Item.objects.create(name=f'Item {i}', sku=f'SKU{i}', is_active=True) for i in range(5)]

    entry_date = date.today()
    for item in items:
        TargetRule.objects.create(
            section=section,
            item=item,
            target_qty=Decimal('100.00'),
            shift_hours=Decimal('8.00'),
            start_date=entry_date
        )

    # Number of forms in the formset
    N = 10

    # Simulate GET request (rendering)
    print(f"--- Simulating rendering of {N} forms ---")
    form_kwargs = {"section": section, "entry_date": entry_date}
    with CaptureQueriesContext(connection) as queries:
        formset = ProductionEntryFormSet(prefix="form", form_kwargs=form_kwargs)
        # Trigger rendering by iterating over forms and accessing fields
        for form in formset:
            # We want to see if choices are being fetched
            list(form.fields['worker'].choices)
            list(form.fields['item'].choices)
            for field in form:
                str(field)

    print(f"Number of queries for rendering {N} forms: {len(queries)}")
    # for q in queries:
    #     print(q['sql'])

    # Simulate POST request (validation)
    print(f"\n--- Simulating validation of {N} forms ---")
    data = {
        'form-TOTAL_FORMS': str(N),
        'form-INITIAL_FORMS': '0',
        'form-MIN_NUM_FORMS': '1',
        'form-MAX_NUM_FORMS': '1000',
    }
    for i in range(N):
        data[f'form-{i}-worker'] = str(workers[i % 5].id)
        data[f'form-{i}-item'] = str(items[i % 5].id)
        data[f'form-{i}-actual_qty'] = '80.00'
        data[f'form-{i}-target_qty'] = '100.00'
        data[f'form-{i}-shift_hours'] = '8.00'

    with CaptureQueriesContext(connection) as queries:
        formset = ProductionEntryFormSet(data, prefix="form", form_kwargs=form_kwargs)
        is_valid = formset.is_valid()
        if is_valid:
            for form in formset:
                _ = form.cleaned_data
        else:
            print(formset.errors)

    print(f"Number of queries for validating {N} forms: {len(queries)}")
    for i, q in enumerate(queries):
        print(f"{i}: {q['sql']}")
    # for q in queries:
    #    print(q['sql'])

if __name__ == "__main__":
    reproduce()
