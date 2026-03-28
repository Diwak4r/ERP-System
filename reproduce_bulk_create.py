import os
import django
from decimal import Decimal
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append('testserver')

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.db import connection
from production.models import Section, Worker, Item, TargetRule, ProductionEntry

User = get_user_model()

def reproduce():
    # Setup
    user, _ = User.objects.get_or_create(username='bolt', is_superuser=True)
    user.set_password('pass')
    user.save()

    section, _ = Section.objects.get_or_create(name='Assembly', code='ASM')
    worker, _ = Worker.objects.get_or_create(name='John', employee_code='W001')
    item, _ = Item.objects.get_or_create(name='Widget', sku='ITM-001')
    TargetRule.objects.get_or_create(section=section, item=item, target_qty=100, shift_hours=8, start_date=date.today())

    client = Client()
    client.force_login(user)

    # Prepare data for 10 entries
    data = {
        'entry_date': date.today().isoformat(),
        'section': section.id,
        'form-TOTAL_FORMS': '10',
        'form-INITIAL_FORMS': '0',
        'form-MIN_NUM_FORMS': '0',
        'form-MAX_NUM_FORMS': '1000',
    }
    for i in range(10):
        data[f'form-{i}-worker'] = worker.id
        data[f'form-{i}-item'] = item.id
        data[f'form-{i}-actual_qty'] = '100'
        data[f'form-{i}-target_qty'] = '0'
        data[f'form-{i}-shift_hours'] = '0'

    # Measure queries
    from django.test.utils import CaptureQueriesContext
    with CaptureQueriesContext(connection) as queries:
        response = client.post(reverse('production:entry'), data=data)

    print(f"Total queries for saving 10 entries: {len(queries)}")
    # for q in queries:
    #     print(q['sql'])

if __name__ == '__main__':
    reproduce()
