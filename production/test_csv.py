import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from production.models import Item, Machine, Section

pytestmark = pytest.mark.django_db

@pytest.fixture
def admin_user(db):
    User = get_user_model()
    user = User.objects.create_user(username="csvadmin", password="password")
    group, _ = Group.objects.get_or_create(name="ADMIN")
    user.groups.add(group)
    return user

@pytest.fixture
def standard_user(db):
    User = get_user_model()
    user = User.objects.create_user(username="standard", password="password")
    return user

def test_rbac_enforcement(client, standard_user):
    client.force_login(standard_user)

    url = reverse("production:csv-import-export")
    response = client.get(url)
    assert response.status_code == 302
    assert "login" in response.url

    url = reverse("production:csv-template", kwargs={"model_name": "item"})
    response = client.get(url)
    assert response.status_code == 302

    url = reverse("production:csv-export", kwargs={"model_name": "item"})
    response = client.get(url)
    assert response.status_code == 302

def test_csv_template_generation(client, admin_user):
    client.force_login(admin_user)
    url = reverse("production:csv-template", kwargs={"model_name": "item"})
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert "attachment; filename=\"item_template.csv\"" in response["Content-Disposition"]

    content = response.content.decode("utf-8")
    assert "name,sku,unit,is_active" in content

def test_csv_export(client, admin_user):
    Item.objects.create(name="Test Item", sku="ITEM1", unit="KG", is_active=True)

    client.force_login(admin_user)
    url = reverse("production:csv-export", kwargs={"model_name": "item"})
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"

    content = response.content.decode("utf-8")
    assert "name,sku,unit,is_active" in content
    assert "Test Item,ITEM1,KG,True" in content

def test_valid_csv_import(client, admin_user):
    client.force_login(admin_user)

    csv_content = b"name,sku,unit,is_active\nNew Item,NEW001,PCS,True"
    csv_file = SimpleUploadedFile("items.csv", csv_content, content_type="text/csv")

    url = reverse("production:csv-import-export")
    response = client.post(url, {
        "model_name": "item",
        "csv_file": csv_file
    }, follow=True)

    messages = list(response.context["messages"]) if "messages" in response.context else []
    print([str(m) for m in messages])

    assert Item.objects.filter(sku="NEW001").exists()

def test_invalid_csv_import_missing_headers(client, admin_user):
    client.force_login(admin_user)

    csv_content = b"name,sku\nBad Item,BAD001"
    csv_file = SimpleUploadedFile("items.csv", csv_content, content_type="text/csv")

    url = reverse("production:csv-import-export")
    response = client.post(url, {
        "model_name": "item",
        "csv_file": csv_file
    })

    assert response.status_code == 302
    assert not Item.objects.filter(sku="BAD001").exists()

def test_transactional_rollback_on_error(client, admin_user):
    client.force_login(admin_user)

    # Second row is invalid (missing SKU is likely a validation error), so first row should not be saved
    csv_content = b"name,sku,unit,is_active\nValid Item,VAL001,PCS,True\nMissing SKU,,PCS,True"
    csv_file = SimpleUploadedFile("items.csv", csv_content, content_type="text/csv")

    url = reverse("production:csv-import-export")
    response = client.post(url, {
        "model_name": "item",
        "csv_file": csv_file
    })

    assert response.status_code == 302
    assert not Item.objects.filter(sku="VAL001").exists()

def test_section_foreign_key_mapping(client, admin_user):
    Section.objects.create(name="Main Section", code="S1", is_active=True)

    client.force_login(admin_user)

    csv_content = b"section_code,name,machine_code,is_active\nS1,Machine 1,M1,True"
    csv_file = SimpleUploadedFile("machines.csv", csv_content, content_type="text/csv")

    url = reverse("production:csv-import-export")
    response = client.post(url, {
        "model_name": "machine",
        "csv_file": csv_file
    })

    assert response.status_code == 302
    assert Machine.objects.filter(machine_code="M1").exists()
    machine = Machine.objects.get(machine_code="M1")
    assert machine.section.code == "S1"
